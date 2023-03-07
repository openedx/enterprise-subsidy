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
from rest_framework.routers import DefaultRouter

from enterprise_subsidy.apps.api.v1 import views

app_name = 'v1'

router = DefaultRouter()
router.register(r'subsidies', views.SubsidyViewSet, basename='subsidy')
router.register(r'transactions', views.TransactionViewSet, basename='transaction')

# Add additional patterns for individual views here.
urlpatterns = []

urlpatterns += router.urls
