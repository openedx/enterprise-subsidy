"""
Admin configuration for subsidy models.
"""
import logging

from django.conf import settings
from django.contrib import admin
from djangoql.admin import DjangoQLSearchMixin
from edx_rbac.admin import UserRoleAssignmentAdmin
from simple_history.admin import SimpleHistoryAdmin

from enterprise_subsidy.apps.subsidy.forms import EnterpriseSubsidyRoleAssignmentAdminForm
from enterprise_subsidy.apps.subsidy.models import EnterpriseSubsidyRoleAssignment, Subsidy

from .constants import CENTS_PER_DOLLAR

log = logging.getLogger(__name__)


def cents_to_usd_string(balance_in_cents):
    """
    Helper to convert cents as an int to dollars as a
    nicely formatted string.
    """
    return "${:,.2f}".format(float(balance_in_cents) / CENTS_PER_DOLLAR)


def can_modify():
    return getattr(settings, 'ALLOW_LEDGER_MODIFICATION', False)


@admin.register(Subsidy)
class SubsidyAdmin(DjangoQLSearchMixin, SimpleHistoryAdmin):
    """
    Admin for the Subsidy model.
    """
    class Meta:
        model = Subsidy
        fields = '__all__'

    djangoql_completion_enabled_by_default = False

    _all_fields = [field.name for field in Subsidy._meta.get_fields()]

    if can_modify():
        readonly_fields = ['get_balance_usd', 'starting_balance_usd']
    else:
        readonly_fields = [
            'get_balance_usd',
            'starting_balance_usd',
            'starting_balance',
            'ledger',
            'unit',
            'enterprise_customer_uuid',
        ]

    list_display = (
        'title',
        'uuid',
        'enterprise_customer_uuid',
        'active_datetime',
        'internal_only',
        'is_soft_deleted',
        'modified',
    )
    list_filter = (
        'internal_only',
        'is_soft_deleted',
    )
    search_fields = (
        'uuid',
        'enterprise_customer_uuid',
    )

    def get_queryset(self, request):
        queryset = Subsidy.all_objects.all()
        return queryset.select_related('ledger')

    @admin.display(description='Current balance (dollars)')
    def get_balance_usd(self, obj):
        """Returns this subsidy's ledger current balance as a US Dollar string."""
        return cents_to_usd_string(obj.current_balance())

    @admin.display(description='Starting balance (dollars)')
    def starting_balance_usd(self, obj):
        """Returns this subsidy's starting balance as a US Dollar string."""
        return cents_to_usd_string(obj.starting_balance)

    def get_readonly_fields(self, request, obj=None):
        """
        If obj is falsey, assume we're creating and set
        readonly_fields to the empty list.
        """
        if (not obj) or can_modify():
            return []
        return self.readonly_fields


@admin.register(EnterpriseSubsidyRoleAssignment)
class EnterpriseSubsidyRoleAssignmentAdmin(DjangoQLSearchMixin, UserRoleAssignmentAdmin):
    """
    Django admin for EnterpriseSubsidyRoleAssignment Model.
    """
    list_display = (
        'get_username',
        'role',
        'enterprise_id',
    )

    @admin.display(
        description='User'
    )
    def get_username(self, obj):
        return obj.user.username

    class Meta:
        """
        Meta class for EnterpriseSubsidyRoleAssignmentAdmin.
        """

        model = EnterpriseSubsidyRoleAssignment

    fields = ('user', 'role', 'enterprise_id')
    form = EnterpriseSubsidyRoleAssignmentAdminForm
