import csv
import io
import json
import math
from datetime import datetime, date, timedelta
from decimal import Decimal
from django.utils import timezone
from .models import (
    RawIngestedRecord, NormalizedActivityRecord, Facility, AuditTrail
)
from .emission_factors import (
    FUEL_EMISSION_FACTORS, PROCUREMENT_EMISSION_FACTORS,
    FLIGHT_BASE_FACTORS, FLIGHT_CLASS_MULTIPLIERS,
    HOTEL_EMISSION_FACTORS, CAR_EMISSION_FACTORS,
    AIRPORT_COORDINATES
)

def calculate_haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the Great Circle Distance between two GPS coordinates in kilometers.
    """
    R = 6371.0  # Earth's radius in kilometers
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi / 2.0)**2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2.0)**2
    
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c

def parse_sap_date(date_str):
    """
    Parses common SAP date formats: YYYYMMDD (e.g. 20260415) or DD.MM.YYYY (e.g. 15.04.2026).
    """
    if not date_str:
        raise ValueError("Empty date string")
    
    date_str = str(date_str).strip()
    
    # Format YYYYMMDD
    if len(date_str) == 8 and date_str.isdigit():
        return datetime.strptime(date_str, "%Y%m%d").date()
    
    # Format DD.MM.YYYY or D.M.YYYY
    if '.' in date_str:
        parts = date_str.split('.')
        if len(parts) == 3:
            day = int(parts[0])
            month = int(parts[1])
            year = int(parts[2])
            return date(year, month, day)
            
    # Format YYYY-MM-DD
    if '-' in date_str:
        parts = date_str.split('-')
        if len(parts) == 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
            
    raise ValueError(f"Unsupported SAP date format: {date_str}")

def process_sap_ingestion(job, file_content):
    """
    Processes an SAP flat-file CSV export with German headers.
    """
    csv_file = io.StringIO(file_content)
    # Detect delimiter
    dialect = csv.Sniffer().sniff(file_content[:2048])
    reader = csv.DictReader(csv_file, dialect=dialect)
    
    row_idx = 0
    records_created = 0
    errors_encountered = []

    for row in reader:
        row_idx += 1
        raw_record = RawIngestedRecord.objects.create(
            job=job,
            row_index=row_idx,
            raw_data_text=json.dumps(row)
        )
        
        try:
            # Map standard SAP column headers (including German variations)
            werks = (row.get('WERKS') or row.get('Werks') or '').strip()
            budat_str = (row.get('BUDAT') or row.get('Budat') or '').strip()
            matnr = (row.get('MATNR') or row.get('Matnr') or '').strip()
            maktx = (row.get('MAKTX') or row.get('Maktx') or '').strip()
            menge_str = (row.get('MENGE') or row.get('Menge') or '').strip()
            meins = (row.get('MEINS') or row.get('Meins') or '').strip().upper()
            dmbtr_str = (row.get('DMBTR') or row.get('Dmbtr') or '').strip()
            waers = (row.get('WAERS') or row.get('Waers') or '').strip().upper()

            if not werks or not menge_str or not maktx:
                raise ValueError("Missing critical fields in SAP row: WERKS, MENGE, or MAKTX")

            # Parse Quantity
            # SAP numbers may use European comma for decimals: 1.000,50 or 1000,50
            menge_str_cleaned = menge_str.replace('.', '').replace(',', '.')
            raw_quantity = Decimal(menge_str_cleaned)

            # Parse Cost
            dmbtr_val = Decimal('0.00')
            if dmbtr_str:
                dmbtr_cleaned = dmbtr_str.replace('.', '').replace(',', '.')
                dmbtr_val = Decimal(dmbtr_cleaned)

            # Parse Date
            try:
                activity_date = parse_sap_date(budat_str)
            except Exception as e:
                # Default to job creation date if date is unparseable but flag as suspicious
                activity_date = job.created_at.date()
                raise ValueError(f"Date parsing failed for '{budat_str}': {str(e)}")

            # Resolve Facility via Plant Code (WERKS)
            facility = Facility.objects.filter(plant_code=werks).first()
            
            # Normalization variables
            normalized_quantity = raw_quantity
            normalized_unit = meins
            scope = 'SCOPE_1'
            category = 'Stationary Combustion'
            activity_type = ''
            factor = Decimal('0.00')
            suspicious_flags = []

            if not facility:
                suspicious_flags.append(f"Plant code '{werks}' not registered in facility lookup table.")

            # Identify Material and Emission Factor
            maktx_upper = maktx.upper()
            
            # Helper to map material names
            is_fuel = False
            is_procurement = False
            
            if 'HEIZ' in maktx_upper or 'HEATING' in maktx_upper or 'OIL' in maktx_upper:
                mat_key = 'HEIZOEL'
                is_fuel = True
            elif 'DIESEL' in maktx_upper or 'KRAFTSTOFF' in maktx_upper:
                mat_key = 'DIESEL'
                is_fuel = True
            elif 'GAS' in maktx_upper or 'NATURAL' in maktx_upper or 'ERDGAS' in maktx_upper:
                mat_key = 'ERDGAS'
                is_fuel = True
            elif 'PETROL' in maktx_upper or 'BENZIN' in maktx_upper:
                mat_key = 'PETROL'
                is_fuel = True
            elif 'STAHL' in maktx_upper or 'STEEL' in maktx_upper:
                mat_key = 'STAHL'
                is_procurement = True
            elif 'BETON' in maktx_upper or 'CONCRETE' in maktx_upper:
                mat_key = 'BETON'
                is_procurement = True
            else:
                # Fallback gracefully for unrecognized materials to allow user correction in UI
                scope = 'SCOPE_3'
                category = 'Procured Goods - Unmapped'
                activity_type = f"Unmapped: {maktx}"
                factor = Decimal('0.00')
                normalized_quantity = raw_quantity
                normalized_unit = meins
                suspicious_flags.append(f"Unrecognized material: '{maktx}'. Standard factor zeroed. Please map to a valid category.")

            # Apply unit normalization & emissions factor
            if not category.startswith('Procured Goods - Unmapped'):
                if is_fuel:
                    ef_config = FUEL_EMISSION_FACTORS[mat_key]
                    scope = ef_config['scope']
                    category = ef_config['category']
                    activity_type = ef_config['display_name']
                    factor = Decimal(str(ef_config['factor']))
                    target_unit = ef_config['unit']
                    
                    # Unit Conversion
                    if meins == 'L' or meins == 'LTR' or meins == 'LITRE':
                        normalized_quantity = raw_quantity
                        normalized_unit = 'L'
                    elif meins == 'GAL' or meins == 'USG':
                        normalized_quantity = raw_quantity * Decimal('3.78541')
                        normalized_unit = 'L'
                    elif meins == 'M3' or meins == 'CBM':
                        if target_unit == 'L':
                            normalized_quantity = raw_quantity * Decimal('1000.0')
                            normalized_unit = 'L'
                        else:
                            normalized_quantity = raw_quantity
                            normalized_unit = 'M3'
                    else:
                        suspicious_flags.append(f"Inconsistent fuel unit '{meins}'. Assumed raw unit match.")
                        normalized_quantity = raw_quantity
                        normalized_unit = meins
                        
                elif is_procurement:
                    ef_config = PROCUREMENT_EMISSION_FACTORS[mat_key]
                    scope = ef_config['scope']
                    category = ef_config['category']
                    activity_type = ef_config['display_name']
                    factor = Decimal(str(ef_config['factor']))
                    
                    if meins == 'KG' or meins == 'KILOGRAM':
                        normalized_quantity = raw_quantity
                        normalized_unit = 'KG'
                    elif meins == 'TO' or meins == 'TON' or meins == 'T':
                        normalized_quantity = raw_quantity * Decimal('1000.0')
                        normalized_unit = 'KG'
                    else:
                        suspicious_flags.append(f"Inconsistent procurement unit '{meins}'. Standardized to KG.")
                        normalized_quantity = raw_quantity
                        normalized_unit = 'KG'

            # Anomaly Rules
            if raw_quantity <= 0:
                suspicious_flags.append("SAP row displays zero or negative quantity.")
            if dmbtr_val <= 0:
                suspicious_flags.append("SAP transaction contains negative or zero financial charge.")
            if is_fuel and normalized_unit == 'L' and normalized_quantity > 50000:
                suspicious_flags.append(f"Extremely large single fuel intake ({normalized_quantity} L).")

            co2e_kg = normalized_quantity * factor
            review_status = 'PENDING_REVIEW'
            suspicious_reason = ""
            
            if suspicious_flags:
                review_status = 'SUSPICIOUS'
                raw_record.status = 'SUSPICIOUS'
                raw_record.validation_errors = "; ".join(suspicious_flags)
                raw_record.save()
                suspicious_reason = "; ".join(suspicious_flags)

            # Create Normalized Activity Record
            norm_rec = NormalizedActivityRecord.objects.create(
                organization=job.organization,
                raw_record=raw_record,
                facility=facility,
                scope=scope,
                category=category,
                activity_type=activity_type,
                start_date=activity_date,
                end_date=activity_date,
                raw_quantity=raw_quantity,
                raw_unit=meins,
                normalized_quantity=normalized_quantity,
                normalized_unit=normalized_unit,
                co2e_kg=co2e_kg,
                emission_factor_used=factor,
                review_status=review_status,
                suspicious_reason=suspicious_reason
            )

            # Create standard audit trail log for record ingestion
            AuditTrail.objects.create(
                activity_record=norm_rec,
                action='CREATE',
                change_reason=f"System ingested SAP material document {row.get('MBLNR', 'N/A')} row."
            )
            records_created += 1

        except Exception as e:
            raw_record.status = 'ERROR'
            raw_record.validation_errors = str(e)
            raw_record.save()
            errors_encountered.append(f"Row {row_idx}: {str(e)}")

    if errors_encountered:
        job.status = 'FAILED'
        job.error_summary = "\n".join(errors_encountered[:10]) + (f"\n...and {len(errors_encountered)-10} more" if len(errors_encountered) > 10 else "")
    else:
        job.status = 'SUCCESS'
    job.save()
    return records_created

def proration_date_range(start_dt, end_dt):
    """
    Given two date objects, yield a list of tuples detailing the dates matching each month:
    [((year, month), list_of_dates)]
    """
    delta = end_dt - start_dt
    days_list = [start_dt + timedelta(days=i) for i in range(delta.days + 1)]
    
    months_map = {}
    for d in days_list:
        key = (d.year, d.month)
        if key not in months_map:
            months_map[key] = []
        months_map[key].append(d)
        
    return months_map

def process_utility_ingestion(job, file_content):
    """
    Processes a PG&E-style Utility billing portal CSV.
    Computes exact calendar-month proration and generates prorated Scope 2 ledgers.
    """
    csv_file = io.StringIO(file_content)
    dialect = csv.Sniffer().sniff(file_content[:2048])
    reader = csv.DictReader(csv_file, dialect=dialect)
    
    row_idx = 0
    records_created = 0
    errors_encountered = []

    for row in reader:
        row_idx += 1
        raw_record = RawIngestedRecord.objects.create(
            job=job,
            row_index=row_idx,
            raw_data_text=json.dumps(row)
        )
        
        try:
            # Map standard fields
            sa_id = (row.get('Service_Agreement_ID') or row.get('Service Agreement ID') or '').strip()
            meter_num = (row.get('Meter_Number') or row.get('Meter Number') or '').strip()
            start_date_str = (row.get('Billing_Start_Date') or row.get('Billing Start Date') or '').strip()
            end_date_str = (row.get('Billing_End_Date') or row.get('Billing End Date') or '').strip()
            usage_str = (row.get('Total_Usage_kWh') or row.get('Total Usage (kWh)') or row.get('Usage') or '').strip()
            charges_str = (row.get('Total_Charges_USD') or row.get('Total Charges ($)') or '').strip()
            tariff = (row.get('Tariff_Rate_Plan') or row.get('Tariff') or '').strip()

            if not sa_id or not meter_num or not start_date_str or not end_date_str or not usage_str:
                raise ValueError("Missing critical fields in Utility CSV row.")

            # Parse numbers
            total_usage_kwh = Decimal(usage_str.replace(',', ''))
            total_charges = Decimal(charges_str.replace(',', '').replace('$', '')) if charges_str else Decimal('0.00')

            # Parse dates
            start_dt = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").date()

            if end_dt <= start_dt:
                raise ValueError(f"Billing End Date ({end_date_str}) must be after Start Date ({start_date_str})")

            # Map meter to Facility dynamically
            # If meter contains plant identifier (e.g. MET-US02), extract it. Otherwise lookup or manual map.
            facility = None
            for fac in Facility.objects.all():
                if fac.plant_code in meter_num or fac.plant_code in sa_id:
                    facility = fac
                    break
            
            # If not dynamically mapped, try mapping by plant code substring
            if not facility:
                if 'US02' in meter_num:
                    facility = Facility.objects.filter(plant_code='US02').first()
                elif 'DE01' in meter_num:
                    facility = Facility.objects.filter(plant_code='DE01').first()
                elif 'IN03' in meter_num:
                    facility = Facility.objects.filter(plant_code='IN03').first()

            suspicious_flags = []
            if not facility:
                suspicious_flags.append(f"Meter '{meter_num}' not dynamically mapped to any registered Plant.")

            # Calculate daily proration
            months_data = proration_date_range(start_dt, end_dt)
            total_billing_days = sum(len(days) for days in months_data.values())
            
            if total_billing_days <= 0:
                raise ValueError("Calculated billing days are zero.")

            daily_kwh = total_usage_kwh / Decimal(str(total_billing_days))
            daily_charges = total_charges / Decimal(str(total_billing_days))

            # Anomaly Checks
            if total_usage_kwh <= 0:
                suspicious_flags.append("Utility reading shows zero or negative electricity consumption.")
            if total_charges <= 0:
                suspicious_flags.append("Utility charges are negative or zero.")
            if daily_kwh > 500:  # > 500 kWh/day is a high threshold for standard operations
                suspicious_flags.append(f"High daily energy consumption detected: {round(daily_kwh, 2)} kWh/day.")

            # Create prorated entries
            for (year, month), dates_list in months_data.items():
                prorated_days = len(dates_list)
                prorated_kwh = daily_kwh * Decimal(str(prorated_days))
                prorated_cost = daily_charges * Decimal(str(prorated_days))
                
                sub_start = min(dates_list)
                sub_end = max(dates_list)

                # Determine grid emission factor based on mapped facility
                if facility:
                    ef = facility.grid_emission_factor
                else:
                    ef = Decimal('0.400')  # Default grid factor
                
                co2e_kg = prorated_kwh * ef
                
                row_review_status = 'PENDING_REVIEW'
                row_suspicious_reason = ""
                
                if suspicious_flags:
                    row_review_status = 'SUSPICIOUS'
                    raw_record.status = 'SUSPICIOUS'
                    raw_record.validation_errors = "; ".join(suspicious_flags)
                    raw_record.save()
                    row_suspicious_reason = "; ".join(suspicious_flags)

                # Create separate entry for this month
                norm_rec = NormalizedActivityRecord.objects.create(
                    organization=job.organization,
                    raw_record=raw_record,
                    facility=facility,
                    scope='SCOPE_2',
                    category='Purchased Electricity',
                    activity_type='Purchased Grid Electricity',
                    start_date=sub_start,
                    end_date=sub_end,
                    raw_quantity=total_usage_kwh,
                    raw_unit='kWh',
                    normalized_quantity=prorated_kwh,
                    normalized_unit='kWh',
                    co2e_kg=co2e_kg,
                    emission_factor_used=ef,
                    review_status=row_review_status,
                    suspicious_reason=row_suspicious_reason
                )

                AuditTrail.objects.create(
                    activity_record=norm_rec,
                    action='CREATE',
                    change_reason=f"System prorated billing cycle into {sub_start.strftime('%B %Y')} ledger. Active days: {prorated_days}."
                )
                records_created += 1

        except Exception as e:
            raw_record.status = 'ERROR'
            raw_record.validation_errors = str(e)
            raw_record.save()
            errors_encountered.append(f"Row {row_idx}: {str(e)}")

    if errors_encountered:
        job.status = 'FAILED'
        job.error_summary = "\n".join(errors_encountered[:10]) + (f"\n...and {len(errors_encountered)-10} more" if len(errors_encountered) > 10 else "")
    else:
        job.status = 'SUCCESS'
    job.save()
    return records_created

def process_concur_travel_ingestion(job, file_content):
    """
    Processes corporate travel segment JSON payloads (Concur / Navan format).
    Calculates great circle flight distance via Haversine and assigns hotels and rentals.
    """
    try:
        data = json.loads(file_content)
    except Exception as e:
        job.status = 'FAILED'
        job.error_summary = f"Invalid JSON format: {str(e)}"
        job.save()
        return 0

    # Accommodate direct dictionary or a list wrapper
    trips = data.get('trips') or data.get('Bookings') or []
    if not isinstance(trips, list):
        if 'TripId' in data:
            trips = [data]
        else:
            job.status = 'FAILED'
            job.error_summary = "Expected high-level list or structure of trips."
            job.save()
            return 0

    row_idx = 0
    records_created = 0
    errors_encountered = []

    for trip in trips:
        row_idx += 1
        raw_record = RawIngestedRecord.objects.create(
            job=job,
            row_index=row_idx,
            raw_data_text=json.dumps(trip)
        )
        
        try:
            segments = trip.get('segments') or trip.get('Bookings') or []
            trip_id = trip.get('TripId') or trip.get('ItineraryId') or f"TRIP-{row_idx}"
            user_email = trip.get('UserEmail') or trip.get('EmployeeEmail') or 'employee@corporate.com'
            
            # Map employee email to a facility (for Scope 3 mapping)
            # Default to assigning it to first facility if unable to map.
            facility = Facility.objects.first()

            for seg in segments:
                seg_type = seg.get('SegmentType') or seg.get('segment_type') or ''
                seg_type = seg_type.upper()
                
                suspicious_flags = []
                scope = 'SCOPE_3'
                category = ''
                activity_type = ''
                
                raw_qty = Decimal('0.00')
                raw_unit = ''
                norm_qty = Decimal('0.00')
                norm_unit = ''
                factor = Decimal('0.00')
                co2e_kg = Decimal('0.00')
                
                start_dt = None
                end_dt = None

                # 1. FLIGHT / AIR SEGMENT
                if seg_type == 'AIR' or seg_type == 'FLIGHT':
                    category = 'Business Travel - Flight'
                    dep = (seg.get('DepartureAirport') or seg.get('from_airport') or '').strip().upper()
                    arr = (seg.get('ArrivalAirport') or seg.get('to_airport') or '').strip().upper()
                    cabin = (seg.get('ClassOfService') or seg.get('cabin_class') or 'ECONOMY').strip().upper()
                    
                    dep_time_str = seg.get('DepartureTime') or seg.get('departure_date')
                    
                    if dep_time_str:
                        start_dt = datetime.strptime(dep_time_str[:10], "%Y-%m-%d").date()
                        end_dt = start_dt
                    else:
                        start_dt = job.created_at.date()
                        end_dt = start_dt

                    if not dep or not arr:
                        raise ValueError("Missing departure or arrival airport code.")

                    # Calculate Distance using Haversine
                    dep_gps = AIRPORT_COORDINATES.get(dep)
                    arr_gps = AIRPORT_COORDINATES.get(arr)
                    
                    distance_km = 0.0
                    if not dep_gps or not arr_gps:
                        suspicious_flags.append(f"Airport codes ({dep} -> {arr}) coordinates not found. Distance zeroed.")
                        raw_qty = Decimal('0.00')
                        raw_unit = 'pass-km'
                    else:
                        distance_km = calculate_haversine_distance(dep_gps[0], dep_gps[1], arr_gps[0], arr_gps[1])
                        raw_qty = Decimal(f"{distance_km:.2f}")
                        raw_unit = 'pass-km'
                    
                    norm_qty = raw_qty
                    norm_unit = 'pass-km'
                    
                    # Flight emission tiers
                    if distance_km < 500:
                        flight_tier = 'SHORT'
                    elif distance_km < 3700:
                        flight_tier = 'MEDIUM'
                    else:
                        flight_tier = 'LONG'
                        
                    base_factor = Decimal(str(FLIGHT_BASE_FACTORS[flight_tier]))
                    multiplier = Decimal(str(FLIGHT_CLASS_MULTIPLIERS.get(cabin, 1.0)))
                    factor = base_factor * multiplier
                    co2e_kg = norm_qty * factor
                    activity_type = f"Flight: {dep}-{arr} ({cabin})"

                # 2. HOTEL SEGMENT
                elif seg_type == 'HOTEL' or seg_type == 'ACCOMMODATION':
                    category = 'Business Travel - Hotel'
                    hotel_name = seg.get('HotelName') or seg.get('hotel_name') or 'Corporate Lodging'
                    nights_str = seg.get('RoomNights') or seg.get('nights') or '1'
                    country = (seg.get('Country') or seg.get('country') or 'DEFAULT').strip().upper()
                    
                    in_date_str = seg.get('CheckInDate') or seg.get('check_in')
                    out_date_str = seg.get('CheckOutDate') or seg.get('check_out')

                    if in_date_str and out_date_str:
                        start_dt = datetime.strptime(in_date_str[:10], "%Y-%m-%d").date()
                        end_dt = datetime.strptime(out_date_str[:10], "%Y-%m-%d").date()
                    else:
                        start_dt = job.created_at.date()
                        end_dt = start_dt + timedelta(days=int(nights_str))

                    if end_dt < start_dt:
                        suspicious_flags.append("Hotel check-out date is listed before check-in date.")
                    
                    nights = int(nights_str)
                    if nights <= 0:
                        raise ValueError("Room nights must be greater than zero.")
                        
                    raw_qty = Decimal(nights)
                    raw_unit = 'nights'
                    norm_qty = raw_qty
                    norm_unit = 'nights'
                    
                    base_factor = HOTEL_EMISSION_FACTORS.get(country, HOTEL_EMISSION_FACTORS['DEFAULT'])
                    factor = Decimal(str(base_factor))
                    co2e_kg = norm_qty * factor
                    activity_type = f"Hotel: {hotel_name} ({country})"

                # 3. GROUND TRANSPORT / CAR RENTAL
                elif seg_type == 'CAR' or seg_type == 'RENTAL':
                    category = 'Business Travel - Ground'
                    vendor = seg.get('Vendor') or 'Car Rental'
                    car_class = (seg.get('VehicleClass') or seg.get('car_class') or 'ECONOMY').strip().upper()
                    dist_val = seg.get('Distance') or seg.get('distance') or '0'
                    dist_unit = (seg.get('DistanceUnit') or seg.get('distance_unit') or 'KM').strip().upper()

                    start_date_str = seg.get('PickupDate') or seg.get('pickup_date')
                    if start_date_str:
                        start_dt = datetime.strptime(start_date_str[:10], "%Y-%m-%d").date()
                        end_dt = start_dt
                    else:
                        start_dt = job.created_at.date()
                        end_dt = start_dt

                    raw_qty = Decimal(str(dist_val))
                    raw_unit = dist_unit.lower()

                    if dist_unit == 'MILE' or dist_unit == 'MILES':
                        norm_qty = raw_qty * Decimal('1.60934')
                        norm_unit = 'km'
                    else:
                        norm_qty = raw_qty
                        norm_unit = 'km'

                    base_factor = CAR_EMISSION_FACTORS.get(car_class, CAR_EMISSION_FACTORS['ECONOMY'])
                    factor = Decimal(str(base_factor))
                    co2e_kg = norm_qty * factor
                    activity_type = f"Car: {vendor} ({car_class})"

                    if raw_qty <= 0:
                        suspicious_flags.append("Ground transport mileage is missing or zero.")
                    elif norm_qty > 1000:
                        suspicious_flags.append(f"Excessive ground travel mileage ({norm_qty} km).")

                else:
                    continue

                row_review_status = 'PENDING_REVIEW'
                row_suspicious_reason = ""
                
                if suspicious_flags:
                    row_review_status = 'SUSPICIOUS'
                    raw_record.status = 'SUSPICIOUS'
                    raw_record.validation_errors = "; ".join(suspicious_flags)
                    raw_record.save()
                    row_suspicious_reason = "; ".join(suspicious_flags)

                # Create the Normalized Ledger Record
                norm_rec = NormalizedActivityRecord.objects.create(
                    organization=job.organization,
                    raw_record=raw_record,
                    facility=facility,
                    scope=scope,
                    category=category,
                    activity_type=activity_type,
                    start_date=start_dt,
                    end_date=end_dt,
                    raw_quantity=raw_qty,
                    raw_unit=raw_unit,
                    normalized_quantity=norm_qty,
                    normalized_unit=norm_unit,
                    co2e_kg=co2e_kg,
                    emission_factor_used=factor,
                    review_status=row_review_status,
                    suspicious_reason=row_suspicious_reason
                )

                AuditTrail.objects.create(
                    activity_record=norm_rec,
                    action='CREATE',
                    change_reason=f"System ingested Travel Segment ({seg_type}) under trip ID {trip_id}."
                )
                records_created += 1

        except Exception as e:
            raw_record.status = 'ERROR'
            raw_record.validation_errors = str(e)
            raw_record.save()
            errors_encountered.append(f"Trip row {row_idx}: {str(e)}")

    if errors_encountered:
        job.status = 'FAILED'
        job.error_summary = "\n".join(errors_encountered[:10]) + (f"\n...and {len(errors_encountered)-10} more" if len(errors_encountered) > 10 else "")
    else:
        job.status = 'SUCCESS'
    job.save()
    return records_created
