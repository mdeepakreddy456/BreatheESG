import json
from django.db import models
from django.contrib.auth.models import User

class Organization(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Facility(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='facilities')
    plant_code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    region = models.CharField(max_length=100)
    grid_emission_factor = models.DecimalField(max_digits=8, decimal_places=5)  # kg CO2e per kWh

    def __str__(self):
        return f"{self.name} ({self.plant_code})"

class IngestionJob(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed')
    ]
    SOURCE_CHOICES = [
        ('SAP', 'SAP ERP Fuel & Procurement'),
        ('UTILITY', 'Utility Billing Portal'),
        ('TRAVEL', 'Corporate Travel API')
    ]
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='ingestion_jobs')
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    filename = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    ingested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    error_summary = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.source_type} Job {self.id} ({self.status})"

class RawIngestedRecord(models.Model):
    STATUS_CHOICES = [
        ('VALIDATED', 'Validated'),
        ('ERROR', 'Error'),
        ('SUSPICIOUS', 'Suspicious')
    ]
    job = models.ForeignKey(IngestionJob, on_delete=models.CASCADE, related_name='raw_records')
    row_index = models.IntegerField()
    # Serialized JSON text for cross-platform SQLite compatibility
    raw_data_text = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='VALIDATED')
    validation_errors = models.TextField(blank=True, null=True)

    @property
    def raw_data(self):
        try:
            return json.loads(self.raw_data_text)
        except Exception:
            return {}

    @raw_data.setter
    def raw_data(self, val):
        self.raw_data_text = json.dumps(val)

    def __str__(self):
        return f"Job {self.job.id} - Row {self.row_index} ({self.status})"

class NormalizedActivityRecord(models.Model):
    SCOPE_CHOICES = [
        ('SCOPE_1', 'Scope 1 - Direct Emissions'),
        ('SCOPE_2', 'Scope 2 - Indirect Emissions'),
        ('SCOPE_3', 'Scope 3 - Value Chain Emissions')
    ]
    STATUS_CHOICES = [
        ('PENDING_REVIEW', 'Pending Review'),
        ('SUSPICIOUS', 'Suspicious'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected')
    ]
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='normalized_records')
    raw_record = models.ForeignKey(RawIngestedRecord, on_delete=models.CASCADE, related_name='normalized_records')
    facility = models.ForeignKey(Facility, on_delete=models.SET_NULL, null=True, blank=True)
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES)
    category = models.CharField(max_length=100)
    activity_type = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    raw_quantity = models.DecimalField(max_digits=15, decimal_places=4)
    raw_unit = models.CharField(max_length=50)
    normalized_quantity = models.DecimalField(max_digits=15, decimal_places=4)
    normalized_unit = models.CharField(max_length=50)
    co2e_kg = models.DecimalField(max_digits=15, decimal_places=4)
    emission_factor_used = models.DecimalField(max_digits=12, decimal_places=6)
    review_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING_REVIEW')
    suspicious_reason = models.TextField(blank=True, null=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_records')
    approved_at = models.DateTimeField(null=True, blank=True)
    is_locked = models.BooleanField(default=False)
    audit_seal_hash = models.CharField(max_length=64, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.activity_type} - {self.co2e_kg} kg CO2e ({self.review_status})"

class AuditTrail(models.Model):
    ACTION_CHOICES = [
        ('CREATE', 'Created'),
        ('EDIT', 'Modified'),
        ('APPROVE', 'Approved'),
        ('REJECT', 'Rejected'),
        ('LOCK', 'Locked for Audit')
    ]
    activity_record = models.ForeignKey(NormalizedActivityRecord, on_delete=models.CASCADE, related_name='audit_trails')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    # Serialized JSON text for compatibility
    changed_fields_text = models.TextField(blank=True, null=True)
    change_reason = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    @property
    def changed_fields(self):
        if not self.changed_fields_text:
            return {}
        try:
            return json.loads(self.changed_fields_text)
        except Exception:
            return {}

    @changed_fields.setter
    def changed_fields(self, val):
        self.changed_fields_text = json.dumps(val) if val else None

    def __str__(self):
        return f"{self.action} on Record {self.activity_record_id} by {self.user}"
