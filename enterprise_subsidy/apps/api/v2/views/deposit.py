"""
Views for the enterprise-subsidy service relating to the Deposit model
"""
import logging

from django.utils.functional import cached_property
from drf_spectacular.utils import extend_schema
from edx_rbac.decorators import permission_required
from edx_rest_framework_extensions.auth.jwt.authentication import JwtAuthentication
from openedx_ledger.models import Deposit
from requests.exceptions import HTTPError
from rest_framework import generics, permissions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, Throttled

from enterprise_subsidy.apps.api.exceptions import DepositCreationAPIException, ErrorCodes
from enterprise_subsidy.apps.api.utils import get_subsidy_customer_uuid_from_view
from enterprise_subsidy.apps.api.v2.serializers.deposits import (
    DepositCreationError,
    DepositCreationRequestSerializer,
    DepositSerializer
)
from enterprise_subsidy.apps.subsidy.api import get_subsidy_by_uuid
from enterprise_subsidy.apps.subsidy.constants import PERMISSION_CAN_CREATE_DEPOSITS

logger = logging.getLogger(__name__)


class DepositAdminCreate(generics.CreateAPIView):
    """
    A create-only API view for deposits.

    This is only accessible to admins of the related subsidy's enterprise customer.
    """
    authentication_classes = [JwtAuthentication, SessionAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DepositCreationRequestSerializer

    def __init__(self, *args, **kwargs):
        self.extra_context = {}
        super().__init__(*args, **kwargs)

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

    def set_created(self, created):
        """
        Note: This created context setter/getter framework is really only here for when we eventually make deposit
        creation actually idempotent, but for now it's just for show because we only ever pass True from the serializer.
        """
        self.extra_context['created'] = created

    @property
    def created(self):
        return self.extra_context.get('created', True)

    @permission_required(PERMISSION_CAN_CREATE_DEPOSITS, fn=get_subsidy_customer_uuid_from_view)
    @extend_schema(
        tags=['deposits'],
        request=DepositCreationRequestSerializer,
        responses={
            status.HTTP_200_OK: DepositSerializer,
            status.HTTP_201_CREATED: DepositSerializer,
            status.HTTP_403_FORBIDDEN: PermissionDenied,
            status.HTTP_429_TOO_MANY_REQUESTS: Throttled,
            status.HTTP_422_UNPROCESSABLE_ENTITY: APIException,
        },
    )
    def create(self, request, subsidy_uuid):
        """
        A create view that is accessible only to operators of the system.

        It creates (or just gets, if a matching Transaction is found with same ledger and idempotency_key) a
        transaction via the `Subsidy.redeem()` method.  Normally, the logic of this view
        is responsible for determining the price of the requested content key, with which
        the redeemed transaction's quantity will be valued.

        Note that, under some circumstances (for example, assigned learner content), it is
        appropriate and allowable for the *caller* of this view to request a specific price
        at which a redeemed transaction should occur.  In these circumstances, this service
        still does some validation of the requested price to ensure that it falls within
        a reasonable interval around the *true* price of the related content key. See:

        https://github.com/openedx/enterprise-access/blob/main/docs/decisions/0012-assignment-based-policies.rst
        https://github.com/openedx/enterprise-access/blob/main/docs/decisions/0014-assignment-price-validation.rst
        """
        if not self.subsidy.is_active:
            raise DepositCreationAPIException(
                detail='Cannot create a deposit in an inactive subsidy',
                code=ErrorCodes.INACTIVE_SUBSIDY_CREATION_ERROR,
            )
        try:
            response = super().create(request, subsidy_uuid)
            if not self.created:
                response.status_code = status.HTTP_200_OK
            return response  # The default create() response status is HTTP_201_CREATED
        except (HTTPError, DepositCreationError) as exc:
            raise DepositCreationAPIException(detail=str(exc)) from exc
