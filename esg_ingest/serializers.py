from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    Organization, Facility, IngestionJob, RawIngestedRecord,
    NormalizedActivityRecord, AuditTrail
)

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']

class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name', 'created_at']

class FacilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Facility
        fields = ['id', 'plant_code', 'name', 'city', 'country', 'region', 'grid_emission_factor']

class IngestionJobSerializer(serializers.ModelSerializer):
    ingested_by_username = serializers.SerializerMethodField()
    raw_records_count = serializers.SerializerMethodField()
    success_records_count = serializers.SerializerMethodField()

    class Meta:
        model = IngestionJob
        fields = [
            'id', 'source_type', 'filename', 'status', 
            'created_at', 'error_summary', 'ingested_by_username',
            'raw_records_count', 'success_records_count'
        ]

    def get_ingested_by_username(self, obj):
        return obj.ingested_by.username if obj.ingested_by else "System"

    def get_raw_records_count(self, obj):
        return obj.raw_records.count()

    def get_success_records_count(self, obj):
        return obj.raw_records.filter(status='VALIDATED').count()

class RawIngestedRecordSerializer(serializers.ModelSerializer):
    raw_data = serializers.JSONField(read_only=True)  # Explicitly serialize the property

    class Meta:
        model = RawIngestedRecord
        fields = ['id', 'row_index', 'raw_data', 'status', 'validation_errors']

class NormalizedActivityRecordSerializer(serializers.ModelSerializer):
    facility_details = FacilitySerializer(source='facility', read_only=True)
    raw_data_lineage = serializers.SerializerMethodField()
    audit_trails_count = serializers.SerializerMethodField()

    class Meta:
        model = NormalizedActivityRecord
        fields = [
            'id', 'scope', 'category', 'activity_type', 'start_date', 'end_date',
            'raw_quantity', 'raw_unit', 'normalized_quantity', 'normalized_unit',
            'co2e_kg', 'emission_factor_used', 'review_status', 'suspicious_reason',
            'is_locked', 'audit_seal_hash', 'created_at', 'updated_at',
            'facility', 'facility_details', 'raw_record', 'raw_data_lineage', 
            'audit_trails_count'
        ]

    def get_raw_data_lineage(self, obj):
        return obj.raw_record.raw_data if obj.raw_record else {}

    def get_audit_trails_count(self, obj):
        return obj.audit_trails.count()

class AuditTrailSerializer(serializers.ModelSerializer):
    user_username = serializers.SerializerMethodField()
    changed_fields = serializers.JSONField(read_only=True)  # Explicitly serialize the property

    class Meta:
        model = AuditTrail
        fields = ['id', 'action', 'changed_fields', 'change_reason', 'timestamp', 'user_username']

    def get_user_username(self, obj):
        return obj.user.username if obj.user else "System"
