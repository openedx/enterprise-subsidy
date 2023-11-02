"""
Constants that help define the schema for the Subsidy API.
"""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse
from rest_framework import exceptions, status

from .v1.serializers import CanRedeemResponseSerializer, ExceptionSerializer


class Parameters:
    """
    A "namespace" class to hold constants that are OpenApiParameter objects.
    """
    LMS_USER_ID = OpenApiParameter(
        'lms_user_id',
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        required=True,
        allow_blank=False,
        description=(
            "The user identifier to whom the query pertains."
        ),
    )
    CONTENT_KEY = OpenApiParameter(
        'content_key',
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=True,
        allow_blank=False,
        description=(
            "The content key/identifier to which the query pertains."
        ),
    )
    ENTERPRISE_CUSTOMER_UUID = OpenApiParameter(
        'enterprise_customer_uuid',
        type=OpenApiTypes.UUID,
        location=OpenApiParameter.QUERY,
        required=True,
        allow_blank=False,
        description=(
            "The UUID associated with the requesting user's enterprise customer."
        ),
    )


def _open_api_error_response(exception_class, detail_str, example_name):
    """
    Helper that creates an OpenApiResponse, using an ExceptionSerializer,
    so that we get nice error response schema definitions and examples.
    """
    return OpenApiResponse(
        response=ExceptionSerializer(
            exception_class(detail=detail_str)
        ),
        examples=[
            OpenApiExample(
                example_name,
                value={'detail': detail_str},
                status_codes=[exception_class.status_code],
                response_only=True,
            )
        ],
    )


class Responses:
    """
    A namespace to hold OpenApiResponse constants.
    """
    SUBSIDY_CAN_REDEEM_RESPONSES = {
        status.HTTP_200_OK: CanRedeemResponseSerializer,
        status.HTTP_400_BAD_REQUEST: _open_api_error_response(
            exceptions.ParseError,
            'A lms_user_id and content_key are required',
            'can_redeem_parse_error',
        ),
    }
