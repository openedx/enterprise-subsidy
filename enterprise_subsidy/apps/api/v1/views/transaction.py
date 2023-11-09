"""
Views for the enterprise-subsidy service relating to the Transaction model
"""
import logging
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema
from edx_rbac.mixins import PermissionRequiredForListingMixin
from edx_rbac.utils import ALL_ACCESS_CONTEXT, contexts_accessible_from_jwt
from edx_rest_framework_extensions.auth.jwt.authentication import JwtAuthentication
from openedx_ledger.models import LedgerLockAttemptFailed, Transaction
from rest_framework import filters, mixins, permissions, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ParseError
from rest_framework.response import Response

from enterprise_subsidy.apps.api.paginators import TransactionListPaginator
from enterprise_subsidy.apps.api.v1 import utils
from enterprise_subsidy.apps.api.v1.decorators import require_at_least_one_query_parameter
from enterprise_subsidy.apps.api.v1.serializers import TransactionSerializer
from enterprise_subsidy.apps.subsidy.constants import (
    ENTERPRISE_SUBSIDY_ADMIN_ROLE,
    ENTERPRISE_SUBSIDY_LEARNER_ROLE,
    ENTERPRISE_SUBSIDY_OPERATOR_ROLE,
    PERMISSION_CAN_CREATE_TRANSACTIONS,
    PERMISSION_CAN_READ_TRANSACTIONS,
    PERMISSION_NOT_GRANTED
)
from enterprise_subsidy.apps.subsidy.models import (
    ContentNotFoundForCustomerException,
    EnterpriseSubsidyRoleAssignment,
    Subsidy
)

logger = logging.getLogger(__name__)


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
    pagination_class = TransactionListPaginator
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]

    # fields that are queried for search
    search_fields = ['lms_user_email', 'content_title']

    # Settings that control list ordering, powered by OrderingFilter.
    # Fields in `ordering_fields` are what we allow to be passed to the "?ordering=" query param.
    ordering_fields = ['created', 'quantity']
    # `ordering` defines the default order.
    ordering = ['-created']

    # Fields that control permissions for 'list' actions, required by PermissionRequiredForListingMixin.
    list_lookup_field = "ledger__subsidy__enterprise_customer_uuid"
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
    def requested_subsidy_access_policy_uuid(self):
        """
        Fetch the subsidy access policy UUID from the URL query parameters.
        """
        subsidy_access_policy_uuid = self.request.query_params.get("subsidy_access_policy_uuid")
        if subsidy_access_policy_uuid:
            try:
                subsidy_access_policy_uuid = UUID(subsidy_access_policy_uuid)
            except ValueError as exc:
                raise ParseError(f"{subsidy_access_policy_uuid} is not a valid uuid.") from exc
        return subsidy_access_policy_uuid

    @property
    def requested_content_key(self):
        """
        Fetch the content_key from the URL query parameters.
        """
        return self.request.query_params.get("content_key")

    @property
    def requested_lms_user_id(self):
        """
        Fetch the lms_user_id from the URL query parameters.
        """
        return self.request.query_params.get("lms_user_id")

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
        transaction_uuid = self.kwargs.get("uuid")
        if transaction_uuid:
            try:
                transaction_uuid = UUID(transaction_uuid)
            except ValueError as exc:
                raise ParseError(f"{transaction_uuid} is not a valid uuid.") from exc
        return transaction_uuid

    @property
    def requested_subsidy_uuid(self):
        """
        Fetch the subsidy UUID from either the URL query parameters or request body.

        Note: if the request contains both, the query parameter takes priority.
        """
        subsidy_uuid = self.request.query_params.get("subsidy_uuid")
        if not subsidy_uuid:
            subsidy_uuid = self.request.data.get("subsidy_uuid")
        if subsidy_uuid:
            try:
                subsidy_uuid = UUID(subsidy_uuid)
            except ValueError as exc:
                raise ParseError(f"{subsidy_uuid} is not a valid uuid.") from exc
        return subsidy_uuid

    @property
    def base_queryset(self):
        """
        Return a queryset that acts as the "base case".

        From edx-rbac docs: "It should generally return all accessible instances for a user who has access to everything
        within this viewset (like a superuser or admin)."

        In other words, ONLY filter the objects based on explicit request parameters (such as if a specific transaction
        or subsidy UUID has been requested), rather than narrowing the scope of objects based on what contexts the
        requester has permissions against (assume an all-access context)

        EXCEPTION: In the case of a learner calling this view, a special filter is also applied to limit the
        transactions to only their own, within the context the role applies to.  We must not allow learners to view
        other learners' transactions, even if they are part of the same subsidy.
        """
        queryset = Transaction.objects.all()

        #
        # First, filter transactions to prevent learners from being able to read each other's transactions.
        #
        request_jwt = utils.get_decoded_jwt_from_auth_or_cookie(self.request)
        learner_contexts = contexts_accessible_from_jwt(request_jwt, [ENTERPRISE_SUBSIDY_LEARNER_ROLE])
        admin_operator_contexts = contexts_accessible_from_jwt(
            request_jwt,
            [ENTERPRISE_SUBSIDY_ADMIN_ROLE, ENTERPRISE_SUBSIDY_OPERATOR_ROLE],
        )
        learner_only_contexts = set(learner_contexts) - set(admin_operator_contexts)
        if ALL_ACCESS_CONTEXT in admin_operator_contexts:
            # If there are any admin or operator roles mapped to "*" (ALL_ACCESS_CONTEXT), then by definition there are
            # NO contexts for which the learner has ONLY learner access.
            learner_only_contexts = set()
        for learner_only_context in learner_only_contexts:
            # For each context (enterprise_customer_uuid) that the requester only has learner access to, filter
            # transactions related to that context to only include their own transactions.
            # AED 2023-10-31: locally, pylint complains of the binary operation.
            # In github actions, pylint complains of a useless-suppression.
            # Suppressing both and letting the code gods sort it out.
            # pylint: disable=unsupported-binary-operation,useless-suppression
            if request_jwt.get('user_id'):
                queryset = queryset.filter(
                    (
                        Q(ledger__subsidy__enterprise_customer_uuid=learner_only_context)
                        &
                        Q(lms_user_id=request_jwt["user_id"])
                    )
                    |
                    ~Q(ledger__subsidy__enterprise_customer_uuid=learner_only_context)
                )
            else:
                queryset = queryset.filter(
                    ~Q(ledger__subsidy__enterprise_customer_uuid=learner_only_context)
                )
        #
        # Next, filter transactions based on the request parameters.
        #
        request_based_kwargs = {}
        if self.requested_enterprise_customer_uuid:
            request_based_kwargs.update({
                "ledger__subsidy__enterprise_customer_uuid": self.requested_enterprise_customer_uuid
            })
        if self.requested_subsidy_uuid:
            request_based_kwargs.update({"ledger__subsidy__uuid": self.requested_subsidy_uuid})
        if self.requested_transaction_uuid:
            request_based_kwargs.update({"uuid": self.requested_transaction_uuid})
        if self.requested_subsidy_access_policy_uuid:
            request_based_kwargs.update({"subsidy_access_policy_uuid": self.requested_subsidy_access_policy_uuid})
        if self.requested_lms_user_id:
            request_based_kwargs.update({"lms_user_id": self.requested_lms_user_id})
        if self.requested_content_key:
            request_based_kwargs.update({"content_key": self.requested_content_key})

        #
        # Finally, overlay both `user_id`-based and request-parameter-based filters in to one big happy queryset.
        #
        return queryset.filter(
            **request_based_kwargs,
        ).select_related(
            "ledger",
            "ledger__subsidy",
            "reversal",
        ).prefetch_related(
            "external_reference",
            "external_reference__external_fulfillment_provider",
        ).order_by(
            "uuid",
        )

    def retrieve(self, request, *args, **kwargs):  # pylint: disable=useless-parent-delegation
        """
        Retrieve Transactions.

        Implemented as a passthrough to super.

        Endpoint Location: GET /api/v1/transactions/<transaction_uuid>

        Request Arguments:
        - ``transaction_uuid`` (URL location, required):
              The uuid (primary key) of the subsidy from which transactions should be listed.

        Returns:
            rest_framework.response.Response:
                403/404: If the requester does not have permission to access the transaction, or it does not exist.
                200: If a Transaction was successfully retrieved.  Response body is JSON with a serialized Transaction.
        """
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        request=TransactionSerializer,
        responses={
            status.HTTP_200_OK: TransactionSerializer,
        },
    )
    @method_decorator(require_at_least_one_query_parameter('subsidy_uuid'))
    def list(self, request, *args, **kwargs):
        """
        List Transactions.

        Implemented as a passthrough to super, but require a `subsidy_uuid` query param.

        Endpoint Location:
        GET /api/v1/transactions/?subsidy_uuid=<subsidy_uuid>&enterprise_customer_uuid=<enterprise_customer_uui>

        Request Arguments:
        - ``subsidy_uuid`` (query param, required):
              The uuid (primary key) of the subsidy from which transactions should be listed.
        - ``enterprise_customer_uuid`` (query param, optional):
              Filter the output to only include transactions part of subsidies corresponding to the given enterprise
              customer UUID.
        - ``subsidy_access_policy_uuid`` (query param, optional):
              Filter the output to only include transactions created by the given subsidy access policy UUID.
        - ``lms_user_id`` (query_param, optional):
              Filter the output to only include transactions assoicated with the given learner ID.
        - ``content_key`` (query_param, optional):
              Filter the output to only include transactions assoicated with the given content_key.
        - ``include_aggregates`` (query_param, optional):
              If "true", include the ``aggregates`` key (quantities, number of transactions) in the response.

        Response codes:
        - ``400``: If there are missing or otherwise invalid input parameters.  Response body is JSON with a single
        `Error` key.
        - ``200``: In all other cases, return 200 regardless of whether any transactions were found.  Response body is
        JSON with a paginated list of serialized Transactions.
        """
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        """
        Attempt to redeem subsidy for a given user and content.

        This is called to create an enrollment (or entitlement) and associated Transaction.

        Endpoint Location: POST /api/v1/transactions/

        Request Arguments:
        - ``subsidy_uuid`` (POST data, required):
              The uuid (primary key) of the subsidy for which transactions should be created.
        - ``lms_user_id`` (POST data, required):
              The user for whom the transaction is written and for which a fulfillment should occur.
        - ``content_key`` (POST data, required):
              The content for which a fulfillment is created.
        - ``subsidy_access_policy_uuid`` (POST data, required):
              The uuid of the policy that allowed the ledger transaction to be created.

        Returns:
            rest_framework.response.Response:
                400: There are missing or otherwise invalid input parameters.  Response body is JSON with a single
                     `Error` key.
                403: The requester has insufficient create permissions.  Response body is JSON with a single `Error`
                     key.
                422: The subisdy is not redeemable in a way that IS NOT retryable (e.g. the balance is too low, or
                     content is not in catalog, etc.).  Response body is JSON with a
                     single `Error` key.
                429: The subisdy is not redeemable in a way that IS retryable (e.g. something else is already holding a
                     lock on the requested Ledger).  Response body is JSON with a single
                     `Error` key.
                201: A Transaction was successfully created.  Response body is JSON with a serialized Transaction.
        """
        subsidy_uuid = request.data.get("subsidy_uuid")
        lms_user_id = request.data.get("lms_user_id")
        content_key = request.data.get("content_key")
        subsidy_access_policy_uuid = request.data.get("subsidy_access_policy_uuid")
        metadata = request.data.get("metadata")
        if not all([subsidy_uuid, lms_user_id, content_key, subsidy_access_policy_uuid]):
            return Response(
                {
                    "Error": (
                        "One or more required fields were not provided in the request body: "
                        "[subsidy_uuid, lms_user_id, content_key, subsidy_access_policy_uuid]"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            UUID(subsidy_uuid)
            UUID(subsidy_access_policy_uuid)
        except ValueError:
            return Response(
                {"Error": "One or more UUID fields are not valid UUIDs: [subsidy_uuid, subsidy_access_policy_uuid]"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            subsidy = Subsidy.objects.get(uuid=request.data.get("subsidy_uuid"))
        except Subsidy.DoesNotExist:
            return Response(
                {"Error": "The provided subsidy_uuid does not match an existing subsidy."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            transaction, created = subsidy.redeem(
                lms_user_id,
                content_key,
                subsidy_access_policy_uuid,
                metadata=metadata
            )
        except LedgerLockAttemptFailed as exc:
            logger.error(exc)
            return Response(
                {"Error": "Attempt to lock the Ledger failed, please try again."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except ContentNotFoundForCustomerException:
            return Response(
                {"Error": "The given content_key is not in any catalog for this customer."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if not transaction:
            return Response(
                {"Error": "The given content_key is not currently redeemable for the given subsidy."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return Response(
            TransactionSerializer(transaction).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )
