from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from esg_ingest.views import (
    DashboardAnalyticsView, IngestionUploadView,
    FacilityViewSet, IngestionJobViewSet, NormalizedActivityRecordViewSet
)

# Initialize DRF Router for viewsets
router = DefaultRouter()
router.register('facilities', FacilityViewSet, basename='facility')
router.register('jobs', IngestionJobViewSet, basename='job')
router.register('normalized-records', NormalizedActivityRecordViewSet, basename='normalized-record')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/analytics/', DashboardAnalyticsView.as_view(), name='analytics'),
    path('api/ingest/', IngestionUploadView.as_view(), name='ingest'),
    path('api/', include(router.urls)),
]
