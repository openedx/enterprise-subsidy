"""
Views for the enterprise-subsidy service relating to the Transaction model
"""
import logging

from django.utils.functional import cached_property
from django_filters import rest_framework as drf_filters
from drf_spectacular.utils import extend_schema, extend_schema_view
from edx_rbac.decorators import permission_required
from edx_rest_framework_extensions.auth.jwt.authentication import JwtAuthentication
from openedx_ledger.models import LedgerLockAttemptFailed, Transaction
from requests.exceptions import HTTPError
from rest_framework import generics, permissions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, Throttled

from enterprise_subsidy.apps.api.exceptions import ErrorCodes, TransactionCreationAPIException
from enterprise_subsidy.apps.api.filters import TransactionAdminFilterSet
from enterprise_subsidy.apps.api.paginators import TransactionListPaginator
from enterprise_subsidy.apps.api.utils import get_subsidy_customer_uuid_from_view
from enterprise_subsidy.apps.api.v1.serializers import (
    TransactionCreationError,
    TransactionCreationRequestSerializer,
    TransactionSerializer
)
from enterprise_subsidy.apps.fulfillment.api import FulfillmentException
from enterprise_subsidy.apps.subsidy.api import get_subsidy_by_uuid
from enterprise_subsidy.apps.subsidy.constants import (
    PERMISSION_CAN_CREATE_TRANSACTIONS,
    PERMISSION_CAN_READ_ALL_TRANSACTIONS,
    PERMISSION_CAN_READ_TRANSACTIONS
)
from enterprise_subsidy.apps.subsidy.models import ContentNotFoundForCustomerException, Subsidy

logger = logging.getLogger(__name__)


class TransactionBaseViewMixin:
    """
    Base view mixin that defines default authentication and permission classes;
    a subsidy-scoped Transaction queryset; and a default Transaction serializer.
    """
    authentication_classes = [JwtAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TransactionSerializer
    pagination_class = TransactionListPaginator
    queryset = Transaction.objects.all()

    @property
    def requested_subsidy_uuid(self):
        """
        Returns the requested ``subsidy_uuid`` path parameter.
        """
        return self.kwargs.get('subsidy_uuid')

    @cached_property
    def subsidy(self):
        """
        Returns the Subsidy instance from the requested ``subsidy_uuid``.
        """
        return get_subsidy_by_uuid(self.requested_subsidy_uuid, should_raise=True)

    def get_queryset(self):
        """
        A base queryset that selects all transaction records (along with their
        associated ledger, subsidy, reversals, and external references) for the requested ``subsidy_uuid``.
        """
        return Transaction.objects.select_related(
            'ledger',
            'ledger__subsidy',
            'reversal',
        ).prefetch_related(
            'external_reference',
            'external_reference__external_fulfillment_provider',
        ).filter(
            ledger__subsidy=self.subsidy
        )


class TransactionAdminListCreate(TransactionBaseViewMixin, generics.ListCreateAPIView):
    """
    A list view that is accessible only to admins
    of the related subsidy's enterprise customer.  It lists all transactions
    for the requested subsidy, or a subset thereof, depending on the query parameters.
    """
    filter_backends = [drf_filters.DjangoFilterBackend]
    filterset_class = TransactionAdminFilterSet

    def __init__(self, *args, **kwargs):
        self.extra_context = {}
        return super().__init__(*args, **kwargs)

    def get_serializer_class(self):
        if self.request.method.lower() == 'get':
            return TransactionSerializer
        if self.request.method.lower() == 'post':
            return TransactionCreationRequestSerializer

    def set_transaction_was_created(self, created):
        self.extra_context['created'] = created

    @property
    def did_transaction_already_exist(self):
        return self.extra_context.get('created', True) is False

    # https://drf-spectacular.readthedocs.io/en/latest/faq.html#using-extend-schema-on-apiview-has-no-effect
    # @extend_schema needs to be applied to the entrypoint method of the view.
    # For APIView based views, these are get, post, create, etc.
    @extend_schema(
        tags=['transactions'],
        responses={
            status.HTTP_200_OK: TransactionSerializer,
            status.HTTP_403_FORBIDDEN: PermissionDenied,
        },
    )
    def get(self, *args, **kwargs):
        """
        A list view that is accessible only to admins
        of the related subsidy's enterprise customer.  It lists all transactions
        for the requested subsidy, or a subset thereof, depending on the query parameters.

        Note that `TransactionListPaginator`, the pagination_class for this view,
        allows for the inclusion of an `include_aggregates` query parameter,
        which if set to `true`, will include an `aggregates` key in the response
        describing the total quantity of transactions returned in the response `results`.
        """
        return super().get(*args, **kwargs)

    @permission_required(PERMISSION_CAN_READ_ALL_TRANSACTIONS, fn=get_subsidy_customer_uuid_from_view)
    def list(self, request, subsidy_uuid):
        """
        See docstring for get() above.
        """
        return super().list(request, subsidy_uuid)

    @extend_schema(
        tags=['transactions'],
        request=TransactionCreationRequestSerializer,
        responses={
            status.HTTP_200_OK: TransactionSerializer,
            status.HTTP_201_CREATED: TransactionSerializer,
            status.HTTP_403_FORBIDDEN: PermissionDenied,
            status.HTTP_429_TOO_MANY_REQUESTS: Throttled,
            status.HTTP_422_UNPROCESSABLE_ENTITY: APIException,
        },
    )
    def post(self, *args, **kwargs):
        """
        A create view that is accessible only to operators of the system.
        It creates (or just gets, if a matching Transaction is found with same ledger and idempotency_key) a
        transaction via the `Subsidy.redeem()` method.
        """
        return super().post(*args, **kwargs)

    @permission_required(PERMISSION_CAN_CREATE_TRANSACTIONS, fn=get_subsidy_customer_uuid_from_view)
    def create(self, request, subsidy_uuid):
        """
        See docstring for post() above.
        """
        if not self.subsidy.is_active:
            raise TransactionCreationAPIException(
                detail='Cannot create a transaction in an inactive subsidy',
                code=ErrorCodes.INACTIVE_SUBSIDY_CREATION_ERROR,
            )
        try:
            response = super().create(request, subsidy_uuid)
            if self.did_transaction_already_exist:
                response.status_code = status.HTTP_200_OK
            return response
        except LedgerLockAttemptFailed:
            raise Throttled(
                detail='Attempt to lock the Ledger failed, please try again.',
                code=ErrorCodes.LEDGER_LOCK_ERROR,
            )
        except HTTPError as exc:
            raise TransactionCreationAPIException(
                detail=str(exc),
                code=ErrorCodes.ENROLLMENT_ERROR,
            )
        except ContentNotFoundForCustomerException as exc:
            raise TransactionCreationAPIException(
                detail=str(exc),
                code=ErrorCodes.CONTENT_NOT_FOUND,
            )
        except FulfillmentException as exc:
            raise TransactionCreationAPIException(
                detail=str(exc),
                code=ErrorCodes.FULFILLMENT_ERROR,
            )
        except TransactionCreationError as exc:
            raise TransactionCreationAPIException(detail=str(exc))


@extend_schema(
    tags=['transactions'],
    responses={
        status.HTTP_200_OK: TransactionSerializer,
        status.HTTP_403_FORBIDDEN: PermissionDenied,
        status.HTTP_404_NOT_FOUND: NotFound,
    },
)
class TransactionUserList(TransactionBaseViewMixin, generics.ListAPIView):
    """
    Lists all transactions in the given ``subsidy_uuid`` with an ``lms_user_id``
    value equal to the requesting user's lms user id.
    """
    @cached_property
    def lms_user_id(self):
        """ Convenience property to get requesting user's lms_user_id value. """
        return self.request.user.lms_user_id

    def get_queryset(self):
        """
        Returns a queryset of transactions for the ``subsidy_uuid`` of the current request,
        filtered to those records  with an ``lms_user_id``
        value equal to the requesting user's lms user id.
        """
        base_queryset = super().get_queryset()
        return base_queryset.filter(
            lms_user_id=self.lms_user_id,
        )

    @permission_required(PERMISSION_CAN_READ_TRANSACTIONS, fn=get_subsidy_customer_uuid_from_view)
    def list(self, request, subsidy_uuid):
        """
        Lists all transactions in the given ``subsidy_uuid`` with an ``lms_user_id``
        value equal to the requesting user's lms user id.
        """
        if not self.lms_user_id:
            raise NotFound(detail='Could not determine lms_user_id in this request.')
        try:
            return super().list(request, subsidy_uuid)
        except Subsidy.DoesNotExist:
            raise NotFound(detail='The requested Subsidy record does not exist.')
