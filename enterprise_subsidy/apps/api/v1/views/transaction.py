"""
Views for the enterprise-subsidy service relating to the Transaction model
"""
import json
from uuid import UUID

from django.core.exceptions import ValidationError
from edx_rbac.mixins import PermissionRequiredForListingMixin
from edx_rest_framework_extensions.auth.jwt.authentication import JwtAuthentication
from openedx_ledger.models import Transaction
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response

from enterprise_subsidy.apps.api.v1 import utils
from enterprise_subsidy.apps.api.v1.serializers import TransactionSerializer
from enterprise_subsidy.apps.subsidy.constants import (
    ENTERPRISE_SUBSIDY_ADMIN_ROLE,
    ENTERPRISE_SUBSIDY_LEARNER_ROLE,
    ENTERPRISE_SUBSIDY_OPERATOR_ROLE,
    PERMISSION_CAN_CREATE_TRANSACTIONS,
    PERMISSION_CAN_READ_TRANSACTIONS,
    PERMISSION_NOT_GRANTED
)
from enterprise_subsidy.apps.subsidy.models import EnterpriseSubsidyRoleAssignment, Subsidy


class TransactionViewSet(
    PermissionRequiredForListingMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    ViewSet for the Transaction model.

    Currently, this only supports listing, retrieving, creating, and reversing transactions::

      GET  /api/v1/transactions/
      GET  /api/v1/transactions/{transaction_uuid}/
      POST /api/v1/transactions/
      POST /api/v1/transactions/{transaction_uuid}/reverse

    In the future, additional default actions can be added using the following mixins:

    * mixins.UpdateModelMixin (PUT and PATCH)
    * mixins.DestroyModelMixin (DELETE)
    """
    authentication_classes = [JwtAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "uuid"
    serializer_class = TransactionSerializer

    # Fields that control permissions for 'list' actions, required by PermissionRequiredForListingMixin.
    list_lookup_field = "ledger__subisidy__enterprise_customer_uuid"
    allowed_roles = [ENTERPRISE_SUBSIDY_ADMIN_ROLE, ENTERPRISE_SUBSIDY_LEARNER_ROLE, ENTERPRISE_SUBSIDY_OPERATOR_ROLE]
    role_assignment_class = EnterpriseSubsidyRoleAssignment

    def get_permission_required(self):
        """
        Return permissions required for the current requested action.

        We override the function here instead of just setting the ``permission_required`` class attribute because that
        attribute only supports requiring a single permission for the entire viewset.  This override logic allows for
        the permission required to be based conditionally on the type of action.
        """
        permission_for_action = {
            "list": PERMISSION_CAN_READ_TRANSACTIONS,
            "retrieve": PERMISSION_CAN_READ_TRANSACTIONS,
            "create": PERMISSION_CAN_CREATE_TRANSACTIONS,
            "reverse": PERMISSION_CAN_CREATE_TRANSACTIONS,
        }
        permission_required = permission_for_action.get(self.request_action, PERMISSION_NOT_GRANTED)
        return (permission_required,)

    def get_permission_object(self):
        """
        For all non-"list" actions, get a enterprise_customer_uuid to check permissions against.

        Specifically, this determines the context (enterprise_customer_uuid) to pass to the rule predicate(s).  We only
        store the enterprise_customer_uuid in the Subsidy object, so depending on the type of request, different paths
        to resolve the Subsidy are taken.
        """
        enterprise_customer_uuid = None
        subsidy = None
        try:
            # Intentionally do not key off of the request action. Instead, use request args to infer.
            if self.requested_subsidy_uuid:
                # If a specific subsidy was requested, this is probably a "create".
                subsidy = Subsidy.objects.get(uuid=self.requested_subsidy_uuid)
            elif self.requested_transaction_uuid:
                # If a specific transaction was requested, this is probably a "retrieve" or "reverse".
                subsidy = Subsidy.objects.get(ledger__transactions__in=[self.requested_transaction_uuid])
        except Subsidy.DoesNotExist:
            pass
        except ValidationError:
            # This can happen if the uuid in the request body does not parse.
            pass
        else:
            if subsidy:
                enterprise_customer_uuid = str(subsidy.enterprise_customer_uuid)
        return enterprise_customer_uuid

    @property
    def requested_enterprise_customer_uuid(self):
        """
        Look in the query parameters for an enterprise customer UUID.
        """
        return utils.get_enterprise_uuid_from_request_query_params(self.request)

    @property
    def requested_transaction_uuid(self):
        """
        Fetch the transaction UUID from the URL location.

        For detail endpoints, the PK can simply be found in ``self.kwargs``.
        """
        return self.kwargs.get("uuid")

    @property
    def requested_subsidy_uuid(self):
        """
        Fetch the subsidy UUID from the URL location.
        """
        if self.kwargs.get("subsidy_uuid"):
            return self.kwargs.get("subsidy_uuid")
        try:
            return json.loads(self.request.body).get("subsidy_uuid")
        except json.decoder.JSONDecodeError:
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
            kwargs.update({"ledger__subsidy__enterprise_customer_uuid": self.requested_enterprise_customer_uuid})
        if self.requested_transaction_uuid:
            kwargs.update({"uuid": self.requested_transaction_uuid})

        return Transaction.objects.filter(**kwargs).order_by("uuid")

    def create(self, request, *args, **kwargs):
        """
        Attempt to redeem subsidy for a given user and content.

        This is called to create an enrollment (or entitlement) and associated Transaction.

        Endpoint Location: POST /api/v1/transactions/

        Request Arguments:
        - ``subsidy_uuid`` (POST data, required):
              The uuid (primary key) of the subsidy for which transactions should be created.
        - ``learner_id`` (POST data, required):
              The user for whom the transaction is written and for which a fulfillment should occur.
        - ``content_key`` (POST data, required):
              The content for which a fulfillment is created.
        - ``access_policy_uuid`` (POST data, required):
              The uuid of the policy that allowed the ledger transaction to be created.

        Returns:
            rest_framework.response.Response:
                400: If there are missing or otherwise invalid input parameters.  Response body is JSON with a single
                     `Error` key.
                403: If the requester has insufficient create permissions, or the subisdy is not redeemable.  Response
                     body is JSON with a single `Error` key.
                201: If a Transaction was successfully created.  Response body is JSON with a serialized Transaction
                     containing the following keys (sample values):
                     {
                         "uuid": "the-transaction-uuid",
                         "state": "COMMITTED",
                         "idempotency_key": "the-idempotency-key",
                         "lms_user_id": 54321,
                         "content_key": "demox_1234+2T2023",
                         "quantity": 19900,
                         "unit": "USD_CENTS",
                         "reference_id": 1234,
                         "reference_type": "NameOfSomeEnrollmentOrEntitlementModelTBD",
                         "reference_table": "enrollments",
                         "subsidy_access_policy_uuid": "a-policy-uuid",
                         "metadata": {...},
                         "created": "created-datetime",
                         "modified": "modified-datetime",
                         "reversals": []
                     }
        """
        subsidy_uuid = request.data.get("subsidy_uuid")
        learner_id = request.data.get("learner_id")
        content_key = request.data.get("content_key")
        access_policy_uuid = request.data.get("access_policy_uuid")
        if not all([subsidy_uuid, learner_id, content_key, access_policy_uuid]):
            return Response(
                {
                    "Error": (
                        "One or more required fields were not provided in the request body: "
                        "[subsidy_uuid, learner_id, content_key, access_policy_uuid]"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            UUID(subsidy_uuid)
            UUID(access_policy_uuid)
        except ValueError:
            return Response(
                {"Error": "One or more UUID fields are not valid UUIDs: [subsidy_uuid, access_policy_uuid]"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            subsidy = Subsidy.objects.get(uuid=request.data.get("subsidy_uuid"))
        except Subsidy.DoesNotExist:
            return Response(
                {"Error": "The provided subsidy_uuid does not match an existing subsidy."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        transaction, created = subsidy.redeem(learner_id, content_key, access_policy_uuid)
        if not transaction:
            return Response(
                {"Error": "The given content_key is not currently redeemable for the given subsidy."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(
            TransactionSerializer(transaction).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )
