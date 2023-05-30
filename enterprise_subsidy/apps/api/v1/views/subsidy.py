"""
Views for the enterprise-subsidy service relating to the Subsidy model
 service.
"""
from http.client import responses

from django.core.exceptions import MultipleObjectsReturned
from django.utils.functional import cached_property
from drf_spectacular.utils import extend_schema
from edx_rbac.mixins import PermissionRequiredForListingMixin
from edx_rest_framework_extensions.auth.jwt.authentication import JwtAuthentication
from rest_framework import exceptions, mixins, permissions, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.response import Response

from enterprise_subsidy.apps.api.v1 import utils
from enterprise_subsidy.apps.api.v1.exceptions import ServerError
from enterprise_subsidy.apps.api.v1.serializers import (
    CanRedeemResponseSerializer,
    SubsidyCreationRequestSerializer,
    SubsidySerializer,
    SubsidyUpdateRequestSerializer
)
from enterprise_subsidy.apps.subsidy.api import can_redeem, get_or_create_learner_credit_subsidy
from enterprise_subsidy.apps.subsidy.constants import (
    ENTERPRISE_SUBSIDY_ADMIN_ROLE,
    ENTERPRISE_SUBSIDY_OPERATOR_ROLE,
    PERMISSION_CAN_READ_SUBSIDIES,
    PERMISSION_CAN_WRITE_SUBSIDIES,
    PERMISSION_NOT_GRANTED
)
from enterprise_subsidy.apps.subsidy.models import EnterpriseSubsidyRoleAssignment, Subsidy

from ...schema import Parameters, Responses


class CanRedeemResult:
    """
    Simple object for representing data
    sent in the response payload for the can_redeem action.
    DRF Serializers really prefer to operate on objects, not dictionaries,
    when they define a field that is itself a Serializer.
    """
    def __init__(self, can_redeem, content_price, unit, all_transactions):  # pylint: disable=redefined-outer-name
        """ initialize this object """
        self.can_redeem = can_redeem
        self.content_price = content_price
        self.unit = unit
        self.all_transactions = all_transactions


class SubsidyViewSet(
    PermissionRequiredForListingMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
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

    def handle_exception(self, exc):
        response = super().handle_exception(exc)

        if isinstance(exc, ServerError):
            response.data = exc.get_full_details()
        elif response is not None and "detail" in response.data:
            response.data["error_code"] = responses.get(response.status_code, "unknown_error")
            response.data["developer_message"] = response.data["detail"]
            response.data["user_message"] = response.data["detail"]
            del response.data["detail"]
        return response

    def get_serializer_class(self, *args, **kwargs):
        """
        Return the serializer class to use for the current request.

        We override the function here instead of just setting the ``serializer_class`` class attribute because that
        attribute only supports using a single serializer for the entire viewset.  This override logic allows for the
        serializer class to be based conditionally on the type of action.
        """
        if self.request.method.lower() in ('put', 'patch'):
            return SubsidyUpdateRequestSerializer
        if self.request.method.lower() == 'post':
            return SubsidyCreationRequestSerializer
        return super().get_serializer_class(*args, **kwargs)

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
            "create": PERMISSION_CAN_WRITE_SUBSIDIES,
            "update": PERMISSION_CAN_WRITE_SUBSIDIES,
            "destroy": PERMISSION_CAN_WRITE_SUBSIDIES,
            "partial_update": PERMISSION_CAN_WRITE_SUBSIDIES,
        }
        permission_required = permission_for_action.get(self.request_action, PERMISSION_NOT_GRANTED)
        return [permission_required]

    def get_permission_object(self):
        """
        Determine the correct enterprise customer uuid string that role-based
        permissions should be checked against, or None if no such
        customer UUID can be determined from the request payload.
        """
        if self.request_action == 'create':
            try:
                subsidy = Subsidy.objects.get(reference_id=self.request.data['reference_id'])
                context = subsidy.enterprise_customer_uuid
            except Subsidy.DoesNotExist:
                context = self.request.data['default_enterprise_customer_uuid']
        else:
            context = (
                self.requested_enterprise_customer_uuid
                or
                getattr(self.requested_subsidy, 'enterprise_customer_uuid', None)
            )
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

    @extend_schema(
        tags=['subsidy'],
        parameters=[Parameters.LMS_USER_ID, Parameters.CONTENT_KEY],
        responses=Responses.SUBSIDY_CAN_REDEEM_RESPONSES,
    )
    @action(methods=['get'], detail=True)
    def can_redeem(self, request, uuid):  # pylint: disable=unused-argument
        """
        Answers the query "can the given user redeem for the given content_key
        in this subsidy?"

        Returns an object indicating if there is sufficient value remainin in the
        subsidy for this content, along with the quantity/unit required.
        Note that this endpoint will determine the price of the given content key
        from the course-discovery service. The caller of this endpoint need not provide a price.
        """
        lms_user_id = request.query_params.get('lms_user_id')
        content_key = request.query_params.get('content_key')
        if not (lms_user_id and content_key):
            raise exceptions.ParseError(
                detail='A lms_user_id and content_key are required',
            )

        redeemable, content_price, existing_transactions = can_redeem(
            self.requested_subsidy,
            lms_user_id,
            content_key,
        )
        serializer = CanRedeemResponseSerializer(
            CanRedeemResult(
                redeemable,
                content_price,
                self.requested_subsidy.unit,
                existing_transactions,
            )
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=['subsidy'],
        request=SubsidyCreationRequestSerializer,
        responses={
            201: SubsidySerializer,
            200: SubsidySerializer,
            403: exceptions.PermissionDenied,
            400: exceptions.ValidationError,
            500: exceptions.APIException,
        },
    )
    def create(self, request, *args, **kwargs):
        """
        Get or create a new subsidy

        Endpoint Location: POST /api/v1/subsidies/
        """
        if not request.data:
            return Response("Request body is required", status=status.HTTP_400_BAD_REQUEST)
        create_serializer = SubsidyCreationRequestSerializer(data=request.data)
        if create_serializer.is_valid(raise_exception=True):
            try:
                subsidy, created = get_or_create_learner_credit_subsidy(
                    create_serializer.data['reference_id'],
                    create_serializer.data['default_title'],
                    create_serializer.data['default_enterprise_customer_uuid'],
                    create_serializer.data['default_active_datetime'],
                    create_serializer.data['default_expiration_datetime'],
                    create_serializer.data['default_unit'],
                    create_serializer.data['default_starting_balance'],
                    create_serializer.data['default_revenue_category'],
                    create_serializer.data['default_internal_only'],
                )

                if created:
                    return Response(SubsidySerializer(subsidy).data, status=status.HTTP_201_CREATED)
                if subsidy:
                    return Response(SubsidySerializer(subsidy).data, status=status.HTTP_200_OK)
                else:
                    raise ServerError(
                        code="could_not_create_subsidy",
                        developer_message="Could not create subsidy",
                        user_message="Could not create subsidy",
                    )
            except MultipleObjectsReturned as exc:
                raise ServerError(
                        code="multiple_subsidies_found",
                        developer_message="Multiple subsidies with given reference_id found.",
                        user_message="Multiple subsidies with given reference_id found.",
                    ) from exc
            except Exception as exc:
                raise ServerError(
                    code="could_not_create_subsidy",
                    developer_message=f"Subsidy could not be created: {exc}",
                    user_message="Subsidy could not be created.",
                ) from exc
        else:
            return Response(create_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        tags=['subsidy'],
        request=SubsidySerializer,
        responses={
            201: SubsidySerializer,
            200: SubsidySerializer,
            403: exceptions.PermissionDenied,
            400: exceptions.ValidationError,
            500: exceptions.APIException,
        },
    )
    def destroy(self, request, *args, **kwargs):
        """
        Delete a subsidy

        Endpoint Location: DELETE /api/v1/subsidies/{uuid}/
        """
        response = super().destroy(request, kwargs['uuid'])
        return response

    @extend_schema(
        tags=['subsidy'],
        request=SubsidyUpdateRequestSerializer,
        responses={
            200: SubsidySerializer,
            403: exceptions.PermissionDenied,
            400: exceptions.ValidationError,
            500: exceptions.APIException,
        },
    )
    def update(self, request, *args, **kwargs):
        """
        Update a subsidy

        Endpoint Location: PUT /api/v1/subsidies/{uuid}/
        """
        response = super().update(request, *args, **kwargs)
        return response

    @extend_schema(
            tags=['subsidy'],
            request=SubsidyUpdateRequestSerializer,
            responses={
                200: SubsidySerializer,
                403: exceptions.PermissionDenied,
                400: exceptions.ValidationError,
                500: exceptions.APIException,
            },
        )
    def partial_update(self, request, *args, **kwargs):
        """
        Partially update a subsidy

        Endpoint Location: PATCH /api/v1/subsidies/{uuid}/
        """
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)
