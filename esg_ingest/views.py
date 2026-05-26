import hashlib
import json
from datetime import datetime
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.contrib.auth.models import User
from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, JSONParser

from .models import (
    Organization, Facility, IngestionJob, RawIngestedRecord,
    NormalizedActivityRecord, AuditTrail
)
from .serializers import (
    OrganizationSerializer, FacilitySerializer, IngestionJobSerializer,
    NormalizedActivityRecordSerializer, AuditTrailSerializer
)
from .parsers import (
    process_sap_ingestion, process_utility_ingestion, process_concur_travel_ingestion
)

class DashboardAnalyticsView(APIView):
    """
    Computes aggregated high-fidelity ESG intelligence metrics for the analyst dashboard.
    """
    def get(self, request):
        # We assume a single organization for prototype purposes
        org = Organization.objects.first()
        if not org:
            return Response({
                "scope_totals": {"Scope 1": 0, "Scope 2": 0, "Scope 3": 0},
                "facility_distribution": [],
                "monthly_trends": [],
                "status_counts": {"pending": 0, "suspicious": 0, "approved": 0}
            })

        # 1. Total Scope Footprint (in kg CO2e)
        scope_query = NormalizedActivityRecord.objects.filter(
            organization=org
        ).exclude(review_status='REJECTED').values('scope').annotate(total_co2=Sum('co2e_kg'))
        
        scope_totals = {"Scope 1": 0.0, "Scope 2": 0.0, "Scope 3": 0.0}
        for item in scope_query:
            if item['scope'] == 'SCOPE_1':
                scope_totals["Scope 1"] = float(item['total_co2'] or 0.0)
            elif item['scope'] == 'SCOPE_2':
                scope_totals["Scope 2"] = float(item['total_co2'] or 0.0)
            elif item['scope'] == 'SCOPE_3':
                scope_totals["Scope 3"] = float(item['total_co2'] or 0.0)

        # 2. Facility Distribution
        facility_query = NormalizedActivityRecord.objects.filter(
            organization=org
        ).exclude(review_status='REJECTED').values(
            'facility__name', 'facility__plant_code'
        ).annotate(total_co2=Sum('co2e_kg')).order_by('-total_co2')
        
        facility_distribution = []
        for item in facility_query:
            facility_distribution.append({
                "name": item['facility__name'] or "Unmapped Facility",
                "plant_code": item['facility__plant_code'] or "UNMAPPED",
                "value": float(item['total_co2'] or 0.0)
            })

        # 3. Monthly Trends (reflects calendar month proration!)
        trends_query = NormalizedActivityRecord.objects.filter(
            organization=org
        ).exclude(review_status='REJECTED').annotate(
            month=TruncMonth('start_date')
        ).values('month', 'scope').annotate(
            total_co2=Sum('co2e_kg')
        ).order_by('month')

        trends_map = {}
        for item in trends_query:
            if not item['month']:
                continue
            month_str = item['month'].strftime('%Y-%m')
            if month_str not in trends_map:
                trends_map[month_str] = {"month": month_str, "Scope 1": 0.0, "Scope 2": 0.0, "Scope 3": 0.0}
            
            s_label = "Scope 1" if item['scope'] == 'SCOPE_1' else "Scope 2" if item['scope'] == 'SCOPE_2' else "Scope 3"
            trends_map[month_str][s_label] = float(item['total_co2'] or 0.0)

        monthly_trends = sorted(trends_map.values(), key=lambda x: x['month'])

        # 4. Ingestion Status Counts
        status_query = NormalizedActivityRecord.objects.filter(
            organization=org
        ).values('review_status').annotate(count=Count('id'))
        
        status_counts = {"pending": 0, "suspicious": 0, "approved": 0, "rejected": 0, "locked": 0}
        for item in status_query:
            st = item['review_status']
            ct = item['count']
            if st == 'PENDING_REVIEW':
                status_counts["pending"] = ct
            elif st == 'SUSPICIOUS':
                status_counts["suspicious"] = ct
            elif st == 'APPROVED':
                status_counts["approved"] = ct
            elif st == 'REJECTED':
                status_counts["rejected"] = ct
        
        status_counts["locked"] = NormalizedActivityRecord.objects.filter(
            organization=org, is_locked=True
        ).count()

        return Response({
            "scope_totals": scope_totals,
            "facility_distribution": facility_distribution,
            "monthly_trends": monthly_trends,
            "status_counts": status_counts
        })

class IngestionUploadView(APIView):
    """
    Handles CSV or JSON ingestion from SAP, Utility portals, or corporate travel platforms.
    """
    parser_classes = [MultiPartParser, JSONParser]

    def post(self, request):
        source_type = request.data.get('source_type')
        if not source_type:
            return Response({"error": "source_type is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Set default tenant
        org, _ = Organization.objects.get_or_create(name="Default Enterprise Client")
        
        # Set default user (create one if empty for prototype)
        user = User.objects.first()
        if not user:
            user = User.objects.create_superuser('admin', 'admin@breatheesg.com', 'admin123')

        # Read uploaded file content or JSON body
        filename = "api_payload.json"
        file_content = ""

        if 'file' in request.FILES:
            uploaded_file = request.FILES['file']
            filename = uploaded_file.name
            try:
                file_content = uploaded_file.read().decode('utf-8')
            except UnicodeDecodeError:
                try:
                    file_content = uploaded_file.read().decode('latin-1')
                except Exception as e:
                    return Response({"error": f"Failed to decode file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        elif 'file_content' in request.data:
            file_content = request.data['file_content']
            filename = request.data.get('filename', 'manual_paste.csv')
        elif isinstance(request.data.get('trips'), list) or 'TripId' in request.data:
            # Direct JSON payload for Concur travel segments
            file_content = json.dumps(request.data)
            filename = "concur_api_push.json"
        else:
            return Response({"error": "No file uploaded or data supplied"}, status=status.HTTP_400_BAD_REQUEST)

        # Register Ingestion Job
        job = IngestionJob.objects.create(
            organization=org,
            source_type=source_type,
            filename=filename,
            status='PROCESSING',
            ingested_by=user
        )

        try:
            records_created = 0
            if source_type == 'SAP':
                records_created = process_sap_ingestion(job, file_content)
            elif source_type == 'UTILITY':
                records_created = process_utility_ingestion(job, file_content)
            elif source_type == 'TRAVEL':
                records_created = process_concur_travel_ingestion(job, file_content)
            else:
                job.status = 'FAILED'
                job.error_summary = f"Invalid source type: {source_type}"
                job.save()
                return Response({"error": f"Invalid source type {source_type}"}, status=status.HTTP_400_BAD_REQUEST)

            # Check if job marked itself as failed due to parsing errors
            job.refresh_from_db()
            if job.status == 'FAILED':
                return Response({
                    "job_id": job.id,
                    "status": "FAILED",
                    "error_summary": job.error_summary,
                    "message": "Data imported with errors. Check Raw Records logs."
                }, status=status.HTTP_200_OK)

            return Response({
                "job_id": job.id,
                "status": job.status,
                "records_ingested": records_created,
                "message": f"Successfully parsed and normalized {records_created} activity rows."
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            job.status = 'FAILED'
            job.error_summary = f"Fatal system error: {str(e)}"
            job.save()
            return Response({"error": f"Failed to ingest: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class FacilityViewSet(viewsets.ModelViewSet):
    queryset = Facility.objects.all()
    serializer_class = FacilitySerializer

    def perform_create(self, serializer):
        org, _ = Organization.objects.get_or_create(name="Default Enterprise Client")
        serializer.save(organization=org)

class IngestionJobViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = IngestionJob.objects.all().order_by('-created_at')
    serializer_class = IngestionJobSerializer

class NormalizedActivityRecordViewSet(viewsets.ModelViewSet):
    """
    Main controller for analyst actions: review, search, filter, edit, signoff, and lock.
    """
    queryset = NormalizedActivityRecord.objects.all().order_by('-start_date')
    serializer_class = NormalizedActivityRecordSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        scope = self.request.query_params.get('scope')
        review_status = self.request.query_params.get('review_status')
        facility = self.request.query_params.get('facility')
        
        if scope:
            queryset = queryset.filter(scope=scope)
        if review_status:
            queryset = queryset.filter(review_status=review_status)
        if facility:
            queryset = queryset.filter(facility_id=facility)
            
        return queryset

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        """
        Custom update method. Enforces mandatory change justification comments
        and recalculates the carbon equivalence metric dynamically.
        """
        instance = self.get_object()
        
        if instance.is_locked:
            return Response(
                {"error": "This record is locked for auditing and cannot be edited."},
                status=status.HTTP_400_BAD_REQUEST
            )

        change_reason = request.data.get('change_reason')
        if not change_reason or not str(change_reason).strip():
            return Response(
                {"error": "A mandatory change_reason comment must be provided by the analyst."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Set default user (prototype fallback)
        user = request.user if request.user.is_authenticated else User.objects.first()

        # Capture old values for audit trail diff
        old_data = {
            "facility_code": instance.facility.plant_code if instance.facility else None,
            "normalized_quantity": float(instance.normalized_quantity),
            "normalized_unit": instance.normalized_unit,
            "start_date": str(instance.start_date),
            "end_date": str(instance.end_date),
            "review_status": instance.review_status
        }

        # Perform update
        facility_id = request.data.get('facility')
        new_quantity = request.data.get('normalized_quantity')
        new_unit = request.data.get('normalized_unit')
        new_status = request.data.get('review_status', 'PENDING_REVIEW')
        
        if facility_id:
            instance.facility_id = int(facility_id)
        if new_quantity is not None:
            instance.normalized_quantity = Decimal(str(new_quantity))
        if new_unit:
            instance.normalized_unit = str(new_unit)
            
        # Re-parse dates if updated
        if request.data.get('start_date'):
            instance.start_date = datetime.strptime(request.data['start_date'][:10], "%Y-%m-%d").date()
        if request.data.get('end_date'):
            instance.end_date = datetime.strptime(request.data['end_date'][:10], "%Y-%m-%d").date()

        # Dynamic carbon recalculation
        instance.co2e_kg = instance.normalized_quantity * instance.emission_factor_used
        
        # Move out of suspicious status if analyst corrected the plant code or details
        if instance.facility and instance.review_status == 'SUSPICIOUS' and not request.data.get('review_status'):
            instance.review_status = 'PENDING_REVIEW'
            instance.suspicious_reason = ""
        else:
            instance.review_status = new_status

        instance.save()

        # Capture new values
        new_data = {
            "facility_code": instance.facility.plant_code if instance.facility else None,
            "normalized_quantity": float(instance.normalized_quantity),
            "normalized_unit": instance.normalized_unit,
            "start_date": str(instance.start_date),
            "end_date": str(instance.end_date),
            "review_status": instance.review_status
        }

        # Save change log diff in Audit Trail
        AuditTrail.objects.create(
            activity_record=instance,
            user=user,
            action='EDIT',
            changed_fields_text=json.dumps({"old": old_data, "new": new_data}),
            change_reason=change_reason
        )

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """
        Quick transition to Approved state.
        """
        instance = self.get_object()
        if instance.is_locked:
            return Response({"error": "Record is locked"}, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user if request.user.is_authenticated else User.objects.first()
        
        instance.review_status = 'APPROVED'
        instance.approved_by = user
        instance.approved_at = timezone.now()
        instance.save()

        AuditTrail.objects.create(
            activity_record=instance,
            user=user,
            action='APPROVE',
            change_reason="Analyst verified raw sources and signed off on carbon values."
        )

        return Response({"status": "approved", "id": instance.id})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """
        Quick transition to Rejected state.
        """
        instance = self.get_object()
        if instance.is_locked:
            return Response({"error": "Record is locked"}, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user if request.user.is_authenticated else User.objects.first()
        reason = request.data.get('reason', 'Rejected by analyst.')
        
        instance.review_status = 'REJECTED'
        instance.save()

        AuditTrail.objects.create(
            activity_record=instance,
            user=user,
            action='REJECT',
            change_reason=reason
        )

        return Response({"status": "rejected", "id": instance.id})

    @action(detail=False, methods=['post'])
    def bulk_lock(self, request):
        """
        Bulk seals multiple approved rows, making them immutable.
        Generates a secure cryptographic audit hash for transparency.
        """
        record_ids = request.data.get('record_ids', [])
        if not record_ids:
            return Response({"error": "No record_ids list supplied"}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user if request.user.is_authenticated else User.objects.first()
        locked_count = 0
        sealed_records = []

        with transaction.atomic():
            for rec_id in record_ids:
                rec = NormalizedActivityRecord.objects.filter(id=rec_id).first()
                if not rec or rec.is_locked:
                    continue
                
                # Force row approval status before locking
                rec.review_status = 'APPROVED'
                rec.is_locked = True
                
                # Cryptographic seal generation (combines core data elements to prove tampering protection)
                raw_hash_string = f"{rec.scope}|{rec.category}|{rec.activity_type}|{rec.start_date}|{rec.end_date}|{rec.normalized_quantity:.4f}|{rec.co2e_kg:.4f}|{rec.emission_factor_used:.6f}"
                seal = hashlib.sha256(raw_hash_string.encode('utf-8')).hexdigest()
                rec.audit_seal_hash = seal
                rec.save()

                AuditTrail.objects.create(
                    activity_record=rec,
                    user=user,
                    action='LOCK',
                    change_reason=f"Sealed row for environmental auditing. Cryptographic seal: SHA256({seal[:8]}...)"
                )
                locked_count += 1
                sealed_records.append({"id": rec.id, "seal_hash": seal})

        return Response({
            "message": f"Successfully locked and cryptographically sealed {locked_count} ESG ledger rows.",
            "locked_records": sealed_records
        })

    @action(detail=True, methods=['get'])
    def audit_trail(self, request, pk=None):
        """
        Fetches the complete historical change logs and revisions for this specific record.
        """
        instance = self.get_object()
        logs = instance.audit_trails.all().order_by('-timestamp')
        serializer = AuditTrailSerializer(logs, many=True)
        return Response(serializer.data)
