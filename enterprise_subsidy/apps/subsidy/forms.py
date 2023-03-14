"""
Forms to be used in enterprise subsidy Django admin.
"""
from edx_rbac.admin import UserRoleAssignmentAdminForm

from enterprise_subsidy.apps.subsidy.models import EnterpriseSubsidyRoleAssignment


class EnterpriseSubsidyRoleAssignmentAdminForm(UserRoleAssignmentAdminForm):
    """
    Django admin form for EnterpriseSubsidyRoleAssignmentAdmin.
    """

    class Meta:
        """
        Meta class for EnterpriseSubsidyRoleAssignmentAdminForm.
        """
        model = EnterpriseSubsidyRoleAssignment
        fields = "__all__"
