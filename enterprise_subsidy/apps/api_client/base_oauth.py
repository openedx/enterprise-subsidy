"""
Base oauth api client for the subsidy service.
"""
import logging

from django.conf import settings
from edx_rest_api_client.client import OAuthAPIClient

logger = logging.getLogger(__name__)


class ApiClientException(Exception):
    """
    Base API Client Exception thrown if something goes wrong while executing client requests.
    """


class BaseOAuthClient:
    """
    API client for calls to the enterprise service.
    """

    def __init__(self):
        self.client = OAuthAPIClient(
            settings.SOCIAL_AUTH_EDX_OAUTH2_URL_ROOT.strip('/'),
            self.oauth2_client_id,
            self.oauth2_client_secret
        )

    @property
    def oauth2_client_id(self):
        return settings.BACKEND_SERVICE_EDX_OAUTH2_KEY

    @property
    def oauth2_client_secret(self):
        return settings.BACKEND_SERVICE_EDX_OAUTH2_SECRET
