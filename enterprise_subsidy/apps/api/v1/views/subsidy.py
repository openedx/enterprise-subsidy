"""
Views for the enterprise-subsidy service relating to the Subsidy model
 service.
"""
from edx_rbac.mixins import PermissionRequiredForListingMixin
from edx_rest_framework_extensions.auth.jwt.authentication import JwtAuthentication
from rest_framework import mixins, permissions, viewsets
from rest_framework.authentication import SessionAuthentication

from enterprise_subsidy.apps.api.v1 import utils
from enterprise_subsidy.apps.api.v1.serializers import SubsidySerializer
from enterprise_subsidy.apps.subsidy.constants import (
    ENTERPRISE_SUBSIDY_ADMIN_ROLE,
    ENTERPRISE_SUBSIDY_OPERATOR_ROLE,
    PERMISSION_CAN_READ_SUBSIDIES,
    PERMISSION_NOT_GRANTED
)
from enterprise_subsidy.apps.subsidy.models import EnterpriseSubsidyRoleAssignment, Subsidy


class SubsidyViewSet(
    PermissionRequiredForListingMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    """
    ViewSet for the Subsidy model.

    Currently, this only supports listing, reading, and testing subsidies::

      GET /api/v1/subsidies/?enterprise_customer_uuid={uuid}&subsidy_type={"learner_credit","subscription"}
      GET /api/v1/subsidies/{subsidy_uuid}/
      GET /api/v1/subsidies/{subsidy_uuid}/can_redeem/
    """
    authentication_classes = [JwtAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "uuid"
    serializer_class = SubsidySerializer

    # Fields that control permissions for 'list' actions, required by PermissionRequiredForListingMixin.
    list_lookup_field = "enterprise_customer_uuid"
    allowed_roles = [ENTERPRISE_SUBSIDY_ADMIN_ROLE, ENTERPRISE_SUBSIDY_OPERATOR_ROLE]
    role_assignment_class = EnterpriseSubsidyRoleAssignment

    def get_permission_required(self):
        """
        Return permissions required for the current requested action.

        We override the function here instead of just setting the ``permission_required`` class attribute because that
        attribute only supports requiring a single permission for the entire viewset.  This override logic allows for
        the permission required to be based conditionally on the type of action.
        """
        permission_for_action = {
            # Note: right now all actions require the same permission, but I'll leave this complexity in here in
            # anticipation that other write actions will be added soon.
            "list": PERMISSION_CAN_READ_SUBSIDIES,
            "retrieve": PERMISSION_CAN_READ_SUBSIDIES,
        }
        permission_required = permission_for_action.get(self.request_action, PERMISSION_NOT_GRANTED)
        return [permission_required]

    def get_permission_object(self):
        """
        Determine the correct enterprise customer uuid that role-based
        permissions should be checked against.
        """
        if self.requested_enterprise_customer_uuid:
            return self.requested_enterprise_customer_uuid
        try:
            subsidy_record = Subsidy.objects.get(uuid=self.requested_subsidy_uuid)
            return str(subsidy_record.enterprise_customer_uuid)
        except Subsidy.DoesNotExist:
            return None

    @property
    def requested_enterprise_customer_uuid(self):
        """
        Look in the query parameters for an enterprise customer UUID.
        """
        return utils.get_enterprise_uuid_from_request_query_params(self.request)

    @property
    def requested_subsidy_uuid(self):
        """
        Fetch the subsidy UUID from the URL location.

        For detail endpoints, the PK can simply be found in ``self.kwargs``.
        """
        return self.kwargs.get("uuid")

    @property
    def base_queryset(self):
        """
        Required by the ``PermissionRequiredForListingMixin``.
        For non-list actions, this is what's returned by ``get_queryset()``.
        For list actions, some non-strict subset of this is what's returned by ``get_queryset()``.
        """
        kwargs = {}
        if self.requested_enterprise_customer_uuid:
            kwargs.update({"enterprise_customer_uuid": self.requested_enterprise_customer_uuid})
        if self.requested_subsidy_uuid:
            kwargs.update({"uuid": self.requested_subsidy_uuid})

        return Subsidy.objects.filter(**kwargs).prefetch_related(
            # Related objects used for calculating the ledger balance.
            "ledger__transactions",
            "ledger__transactions__reversal",
        ).order_by("uuid")
