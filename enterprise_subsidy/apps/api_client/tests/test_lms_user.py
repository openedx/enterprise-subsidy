from unittest import mock

import ddt
from django.test import TestCase
from requests.exceptions import HTTPError

from enterprise_subsidy.apps.api_client.lms_user import LmsUserApiClient
from test_utils.utils import MockResponse


@ddt.ddt
class LmsUserApiClientTests(TestCase):
    """
    Tests for the lms user api client.
    """
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.user_id = 12345
        cls.user_email = 'user@example.com'

    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_successful_get_user_data(self, mock_oauth_client):
        """
        Test the happy path of getting user data from the lms
        """
        mock_oauth_client.return_value.get.return_value = MockResponse(
            [{
                "name": "Example User",
                "email": "user@example.com",
                "id": 12345,
            }],
            200,
        )
        lms_user_client = LmsUserApiClient()
        response = lms_user_client.get_user_data(self.user_id)
        assert response.get('id') == self.user_id
        mock_oauth_client().get.assert_called_with(
            f'{LmsUserApiClient.accounts_url}?lms_user_id={self.user_id}'
        )

    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_failed_get_user_data(self, mock_oauth_client):
        """
        Test the when something fails getting user data from the lms
        """
        mock_oauth_client.return_value.get.return_value = MockResponse(None, 400)
        lms_user_client = LmsUserApiClient()
        with self.assertRaises(HTTPError):
            lms_user_client.get_user_data(self.user_id)

    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_successful_best_effort_user_data(self, mock_oauth_client):
        """
        Test the happy path of the best effort version
        """
        mock_oauth_client.return_value.get.return_value = MockResponse(
            [{
                "name": "Example User",
                "email": "user@example.com",
                "id": 12345,
            }],
            200,
        )
        lms_user_client = LmsUserApiClient()
        response = lms_user_client.best_effort_user_data(self.user_id)
        assert response.get('id') == self.user_id
        mock_oauth_client().get.assert_called_with(
            f'{LmsUserApiClient.accounts_url}?lms_user_id={self.user_id}'
        )

    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_failed_best_effort_user_data(self, mock_oauth_client):
        """
        Test the that the best effort version fails without exception
        """
        mock_oauth_client.return_value.get.return_value = MockResponse(None, 400)
        lms_user_client = LmsUserApiClient()
        response = lms_user_client.best_effort_user_data(self.user_id)
        assert response is None
