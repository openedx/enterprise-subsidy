"""
URL definitions for enterprise-subsidy API version 2.

Listing transactions for admins and operators:

  GET  /api/v2/subsidies/<subsidy_uuid>/admin/transactions/

Creating transactions for operators:

  POST  /api/v2/subsidies/<subsidy_uuid>/admin/transactions/

User-scoped transactions list:

  GET  /api/v2/subsidies/<subsidy_uuid>/transactions/
"""
from django.urls import path

from enterprise_subsidy.apps.api.v2.views.transaction import TransactionAdminListCreate, TransactionUserList

app_name = 'v2'

# Add additional patterns for individual views here.
urlpatterns = [
    path(
        'subsidies/<subsidy_uuid>/admin/transactions/',
        TransactionAdminListCreate.as_view(),
        name='transaction-admin-list-create',
    ),
    path(
        'subsidies/<subsidy_uuid>/transactions/',
        TransactionUserList.as_view(),
        name='transaction-user-list',
    ),
]
