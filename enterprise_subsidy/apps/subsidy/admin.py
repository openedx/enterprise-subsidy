"""
Admin configuration for subsidy models.
"""
from django.contrib import admin
from edx_rbac.admin import UserRoleAssignmentAdmin
from simple_history.admin import SimpleHistoryAdmin

from enterprise_subsidy.apps.subsidy.forms import EnterpriseSubsidyRoleAssignmentAdminForm
from enterprise_subsidy.apps.subsidy.models import EnterpriseSubsidyRoleAssignment, Subsidy


@admin.register(Subsidy)
class SubsidyAdmin(SimpleHistoryAdmin):
    class Meta:
        model = Subsidy
        fields = '__all__'


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
