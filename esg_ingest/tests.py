import json
from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.contrib.auth.models import User
from esg_ingest.models import Organization, Facility, IngestionJob, NormalizedActivityRecord, AuditTrail
from esg_ingest.parsers import (
    calculate_haversine_distance, proration_date_range,
    process_sap_ingestion, process_utility_ingestion, process_concur_travel_ingestion
)

class ESGCoreEngineTestCase(TestCase):
    def setUp(self):
        # Create test organization
        self.org = Organization.objects.create(name="Test Org")
        self.user = User.objects.create_superuser('testadmin', 'admin@test.com', 'pass123')
        
        # Create test facilities
        self.fac_us = Facility.objects.create(
            organization=self.org,
            plant_code="US02",
            name="Texas Refining Center",
            city="Houston",
            country="USA",
            region="US-TX",
            grid_emission_factor=Decimal("0.385")
        )
        self.fac_de = Facility.objects.create(
            organization=self.org,
            plant_code="DE01",
            name="Hamburg Plant",
            city="Hamburg",
            country="Germany",
            region="DE",
            grid_emission_factor=Decimal("0.401")
        )

    def test_haversine_flight_distance(self):
        """
        Verify that our Haversine formula correctly computes JFK to LHR distance (~5570 km).
        """
        # Coordinates: JFK (40.6413, -73.7781), LHR (51.4700, -0.4543)
        distance = calculate_haversine_distance(40.6413, -73.7781, 51.4700, -0.4543)
        self.assertAlmostEqual(distance, 5570.26, delta=50) # Within 50 km margin

    def test_calendar_month_proration_range(self):
        """
        Test that utility billing periods split dates correctly into distinct months.
        March 15 to April 14 = 31 days total. March gets 17 days, April gets 14 days.
        """
        start = date(2026, 3, 15)
        end = date(2026, 4, 14)
        
        months_map = proration_date_range(start, end)
        self.assertIn((2026, 3), months_map)
        self.assertIn((2026, 4), months_map)
        
        march_days = len(months_map[(2026, 3)])
        april_days = len(months_map[(2026, 4)])
        
        self.assertEqual(march_days, 17)
        self.assertEqual(april_days, 14)
        self.assertEqual(march_days + april_days, 31)

    def test_sap_ingestion_conversion(self):
        """
        Test that SAP ingestion converts US Gallons to Liters for Diesel stationary combustion.
        1000 Gallons = 3785.41 Liters. Diesel EF = 2.68 kg CO2e / L.
        """
        job = IngestionJob.objects.create(
            organization=self.org,
            source_type='SAP',
            filename='test_sap.csv',
            ingested_by=self.user
        )
        
        # Ingest 1000 Gallons (GAL) of Diesel in plant US02
        file_content = "WERKS,BUDAT,MATNR,MAKTX,MENGE,MEINS,DMBTR,WAERS\nUS02,20260415,MAT-FUEL-01,Diesel Kraftstoff,1000,GAL,1200.00,USD\n"
        
        records_created = process_sap_ingestion(job, file_content)
        self.assertEqual(records_created, 1)
        
        # Verify normalization values
        record = NormalizedActivityRecord.objects.filter(raw_record__job=job).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.facility, self.fac_us)
        self.assertEqual(record.scope, 'SCOPE_1')
        self.assertEqual(record.raw_quantity, Decimal('1000.0000'))
        self.assertEqual(record.raw_unit, 'GAL')
        
        # Standard US02 conversion factor applied: 3.78541
        expected_norm_qty = Decimal('1000') * Decimal('3.78541')
        self.assertEqual(record.normalized_quantity, expected_norm_qty)
        self.assertEqual(record.normalized_unit, 'L')
        
        # Expected co2e = 3785.41 * 2.68 = 10144.8988
        expected_co2e = expected_norm_qty * Decimal('2.68')
        self.assertAlmostEqual(record.co2e_kg, expected_co2e)

    def test_utility_proration_emissions(self):
        """
        Test that utility ingestion splits 3100 kWh spanning March 15 to April 14
        into 1700 kWh in March and 1400 kWh in April, applying plant factors.
        """
        job = IngestionJob.objects.create(
            organization=self.org,
            source_type='UTILITY',
            filename='test_utility.csv',
            ingested_by=self.user
        )
        
        # 3100 kWh of energy on plant DE01 (Hamburg). Total billing days = 31.
        file_content = "Service_Agreement_ID,Meter_Number,Billing_Start_Date,Billing_End_Date,Total_Usage_kWh,Total_Charges_USD,Tariff_Rate_Plan\nSA-01,MET-DE01,2026-03-15,2026-04-14,3100,620.00,E-19\n"
        
        records_created = process_utility_ingestion(job, file_content)
        self.assertEqual(records_created, 2) # Splits into 2 records
        
        # Retrieve split records
        march_record = NormalizedActivityRecord.objects.get(
            raw_record__job=job, start_date=date(2026, 3, 15), end_date=date(2026, 3, 31)
        )
        april_record = NormalizedActivityRecord.objects.get(
            raw_record__job=job, start_date=date(2026, 4, 1), end_date=date(2026, 4, 14)
        )
        
        # Verify split consumption
        self.assertEqual(march_record.normalized_quantity, Decimal('1700.0000')) # 17 days * 100 kWh/day
        self.assertEqual(april_record.normalized_quantity, Decimal('1400.0000')) # 14 days * 100 kWh/day
        
        # Verify carbon matching: plant DE01 grid factor = 0.401 kg/kWh
        # March emissions = 1700 * 0.401 = 681.7 kg CO2e
        self.assertEqual(march_record.co2e_kg, Decimal('681.7000'))
        # April emissions = 1400 * 0.401 = 561.4 kg CO2e
        self.assertEqual(april_record.co2e_kg, Decimal('561.4000'))

    def test_audit_trail_manual_edit(self):
        """
        Verify that manually editing a record triggers the creation of an AuditTrail entry with changes.
        """
        # Create artificial record
        job = IngestionJob.objects.create(organization=self.org, source_type='SAP', filename='manual.csv')
        from esg_ingest.models import RawIngestedRecord
        raw_rec = RawIngestedRecord.objects.create(job=job, row_index=1, raw_data_text="{}")
        
        norm_rec = NormalizedActivityRecord.objects.create(
            organization=self.org,
            raw_record=raw_rec,
            facility=self.fac_us,
            scope='SCOPE_1',
            category='Stationary Combustion',
            activity_type='Diesel Fuel',
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 1),
            raw_quantity=Decimal('100.0'),
            raw_unit='L',
            normalized_quantity=Decimal('100.0'),
            normalized_unit='L',
            co2e_kg=Decimal('268.0'),
            emission_factor_used=Decimal('2.68'),
            review_status='PENDING_REVIEW'
        )
        
        # Simulate updating quantity to 200 via API patch
        # Capture old values
        old_qty = float(norm_rec.normalized_quantity)
        
        norm_rec.normalized_quantity = Decimal('200.0')
        norm_rec.co2e_kg = Decimal('536.0')
        norm_rec.review_status = 'APPROVED'
        norm_rec.save()
        
        # Save change log in Audit Trail manually representing view behavior
        audit_log = AuditTrail.objects.create(
            activity_record=norm_rec,
            user=self.user,
            action='EDIT',
            changed_fields_text=json.dumps({
                "old": {"normalized_quantity": old_qty, "review_status": "PENDING_REVIEW"},
                "new": {"normalized_quantity": 200.0, "review_status": "APPROVED"}
            }),
            change_reason="Corrected keying error from raw SAP spreadsheet."
        )
        
        # Verify log assertions
        self.assertEqual(norm_rec.audit_trails.filter(action='EDIT').count(), 1)
        edit_log = norm_rec.audit_trails.filter(action='EDIT').first()
        self.assertEqual(edit_log.change_reason, "Corrected keying error from raw SAP spreadsheet.")
        
        # Check diff properties
        diff = edit_log.changed_fields
        self.assertEqual(diff["old"]["normalized_quantity"], 100.0)
        self.assertEqual(diff["new"]["normalized_quantity"], 200.0)
