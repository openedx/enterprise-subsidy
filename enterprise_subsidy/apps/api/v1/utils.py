"""
Common utility functions for the subsidy API.
"""
import uuid

from edx_rest_framework_extensions.auth.jwt.authentication import get_decoded_jwt_from_auth
from edx_rest_framework_extensions.auth.jwt.cookies import get_decoded_jwt
from rest_framework.exceptions import ParseError


def get_decoded_jwt_from_auth_or_cookie(request):
    """
    Get the JWT token from the request and decode it.  For some reason, this isn't just defined in
    edx_rest_framework_extensions.
    """
    return get_decoded_jwt(request) or get_decoded_jwt_from_auth(request)


def get_enterprise_uuid_from_request_query_params(request):
    """
    Returns the enterprise customer UUID from the ``enterprise_customer_uuid`` query parameter.

    Returns:
        uuid.UUID: The UUID of the enterprise customer, or None if the query parameter is not present.

    Raises:
        rest_framework.exceptions.ParseError: If the requested UUID string is not parseable.
    """
    enterprise_customer_uuid = request.query_params.get('enterprise_customer_uuid')
    if not enterprise_customer_uuid:
        return None
    try:
        return uuid.UUID(enterprise_customer_uuid)
    except ValueError as exc:
        raise ParseError(f'{enterprise_customer_uuid} is not a valid uuid.') from exc
