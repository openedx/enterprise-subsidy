"""
URL definitions for enterprise-subsidy API version 1.

Listing, reading, and testing subsidies::

  GET /api/v1/subsidies/?enterprise_customer_uuid={uuid}&subsidy_type={"learner_credit","subscription"}
  GET /api/v1/subsidies/{subsidy_uuid}/
  GET /api/v1/subsidies/{subsidy_uuid}/can_redeem/

Reading, creating, and reversing Transactions::

  GET  /api/v1/transactions/
  GET  /api/v1/transactions/{transaction_uuid}/
  POST /api/v1/transactions/
  POST /api/v1/transactions/{transaction_uuid}/reverse
"""
from django.urls import path
from rest_framework.routers import DefaultRouter

from enterprise_subsidy.apps.api.v1.views.content_metadata import ContentMetadataViewSet
from enterprise_subsidy.apps.api.v1.views.subsidy import SubsidyViewSet
from enterprise_subsidy.apps.api.v1.views.transaction import TransactionViewSet

app_name = 'v1'

router = DefaultRouter()
router.register(r'subsidies', SubsidyViewSet, basename='subsidy')
router.register(r'transactions', TransactionViewSet, basename='transaction')

# Add additional patterns for individual views here.
urlpatterns = [
    path(
        'content-metadata/<content_identifier>/',
        ContentMetadataViewSet.as_view(),
        name='content-metadata'
    ),
    path(
        'subsidies/<uuid>/aggregates-by-learner',
        SubsidyViewSet.as_view({'get': 'get_aggregates_by_learner'}),
        name='subsidies-aggregates-by-learner'
    ),
]

urlpatterns += router.urls
