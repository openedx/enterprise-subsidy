"""
Views for the enterprise-subsidy service relating to the Subsidy model
 service.
"""
from django.utils.functional import cached_property
from edx_rbac.mixins import PermissionRequiredForListingMixin
from edx_rest_framework_extensions.auth.jwt.authentication import JwtAuthentication
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.response import Response

from enterprise_subsidy.apps.api.v1 import utils
from enterprise_subsidy.apps.api.v1.serializers import SubsidySerializer, TransactionSerializer
from enterprise_subsidy.apps.subsidy.api import can_redeem
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
            "can_redeem": PERMISSION_CAN_READ_SUBSIDIES,
        }
        permission_required = permission_for_action.get(self.request_action, PERMISSION_NOT_GRANTED)
        return [permission_required]

    def get_permission_object(self):
        """
        Determine the correct enterprise customer uuid string that role-based
        permissions should be checked against, or None if no such
        customer UUID can be determined from the request payload.
        """
        if self.requested_enterprise_customer_uuid:
            context = self.requested_enterprise_customer_uuid
        else:
            context = getattr(self.requested_subsidy, 'enterprise_customer_uuid', None)
        return str(context) if context else None

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

    @cached_property
    def requested_subsidy(self):
        """
        Returns the Subsidy instance for the requested subsidy uuid.
        """
        try:
            return Subsidy.objects.get(uuid=self.requested_subsidy_uuid)
        except Subsidy.DoesNotExist:
            return None

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

    @action(methods=['get'], detail=True)
    def can_redeem(self, request, uuid):  # pylint: disable=unused-argument
        """
        /api/v1/subsidies/[subsidy-uuid]/can_redeem/
        Answers the query "can the given user redeem for the given or content in this subsidy?"

        Note that this endpoint will determine the price of the given content key
        from the course-discovery service. The caller of this endpoint need not provide a price.

        Path params:
          uuid (URL path, required): The uuid (primary key) of the subsidy for which
            transactions should be listed.

        GET query params:
          lms_user_id (required): The user to whom the query pertains.
          content_key (required): The content to which the query pertains.

        Returns:
          An object indicating if there is sufficient value remainin in the
          subsidy for this content, along with the quantity/unit required. e.g.

          {
            'can_redeem': true (or false),
            'content_price': 19900,
            'unit': 'USD_CENTS',
          }
        """
        lms_user_id = request.query_params.get('lms_user_id')
        content_key = request.query_params.get('content_key')
        if not (lms_user_id and content_key):
            return Response(
                'A lms_user_id and content_key are required',
                status=status.HTTP_400_BAD_REQUEST,
            )

        redeemable, content_price, existing_transaction = can_redeem(
            self.requested_subsidy,
            lms_user_id,
            content_key,
        )
        response_payload = {
            'can_redeem': redeemable,
            'content_price': content_price,
            'unit': self.requested_subsidy.unit,
            'existing_transaction': TransactionSerializer(
                existing_transaction
            ).data if existing_transaction else None
        }

        return Response(response_payload, status=status.HTTP_200_OK)
