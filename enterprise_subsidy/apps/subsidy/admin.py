"""
Admin configuration for subsidy models.
"""
from django.conf import settings
from django.contrib import admin
from edx_rbac.admin import UserRoleAssignmentAdmin
from simple_history.admin import SimpleHistoryAdmin

from enterprise_subsidy.apps.subsidy.forms import EnterpriseSubsidyRoleAssignmentAdminForm
from enterprise_subsidy.apps.subsidy.models import EnterpriseSubsidyRoleAssignment, Subsidy


def can_modify():
    getattr(settings, 'ALLOW_LEDGER_MODIFICATION', False)


@admin.register(Subsidy)
class SubsidyAdmin(SimpleHistoryAdmin):
    """
    Admin for the Subsidy model.
    """
    class Meta:
        model = Subsidy
        fields = '__all__'

    _all_fields = [field.name for field in Subsidy._meta.get_fields()]
    readonly_fields = list(_all_fields)
    if can_modify():
        readonly_fields = []

    list_display = ('title', 'uuid', 'enterprise_customer_uuid')

    def get_readonly_fields(self, request, obj=None):
        """
        If obj is falsey, assume we're creating and set
        readonly_fields to the empty list.
        """
        if obj:
            return self.readonly_fields
        return []


@admin.register(EnterpriseSubsidyRoleAssignment)
class EnterpriseSubsidyRoleAssignmentAdmin(UserRoleAssignmentAdmin):
    """
    Django admin for EnterpriseSubsidyRoleAssignment Model.
    """
    list_display = (
        'get_username',
        'role',
        'enterprise_id',
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

    get_username.short_description = 'User'
