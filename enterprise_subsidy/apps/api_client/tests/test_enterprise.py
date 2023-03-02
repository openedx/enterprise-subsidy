import os
from unittest import mock
from uuid import uuid4

import ddt
from django.conf import settings
from django.test import TestCase

from enterprise_subsidy.apps.api_client.enterprise import EnterpriseApiClient
from test_utils.utils import MockResponse


@ddt.ddt
class EnterpriseApiClientTests(TestCase):
    """
    Tests for the enterprise api client.
    """
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.enterprise_customer_uuid = uuid4()
        cls.user_id = 3
        cls.user_email = 'ayy@lmao.com'
        cls.courserun_key = 'course-v1:edX+DemoX+Demo_Course'

    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_successful_create_enterprise_enrollment(self, mock_oauth_client):
        """
        Test the enterprise client's ability to handle successful api requests to create course enrollments
        """
        mock_oauth_client.return_value.post.return_value = MockResponse(
            {
                'successes': [{'email': self.user_email, 'course_run_key': self.courserun_key}],
                'pending': [],
                'failures': []
            },
            201,
        )
        options = [{
            'email': self.user_email,
            'course_run_key': self.courserun_key,
            'transaction_id': 'some-transaction-id',
        }]
        enterprise_client = EnterpriseApiClient()
        response = enterprise_client.bulk_enroll_enterprise_learners(self.enterprise_customer_uuid, options)
        assert response.get('successes') == [{'email': self.user_email, 'course_run_key': self.courserun_key}]
        mock_oauth_client().post.assert_called_with(
            os.path.join(EnterpriseApiClient.enterprise_customer_endpoint, str(self.enterprise_customer_uuid)) +
            '/enroll_learners_in_courses/',
            json={'enrollments_info': [{
                'email': self.user_email,
                'course_run_key': self.courserun_key,
                'transaction_id': 'some-transaction-id',
            }]},
            timeout=settings.BULK_ENROLL_REQUEST_TIMEOUT_SECONDS
        )

    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_successful_create_single_learner_enrollment(self, mock_oauth_client):
        """
        Test the enterprise client's ability to handle successful api requests to create a course enrollments
        for a single learner
        """
        mock_oauth_client.return_value.post.return_value = MockResponse(
            {
                'successes': [{'email': self.user_email, 'course_run_key': self.courserun_key}],
                'pending': [],
                'failures': []
            },
            201,
        )

        enterprise_client = EnterpriseApiClient()
        response = enterprise_client.enroll_enterprise_learner_in_courserun(
            'some-transaction-id',
            self.user_email,
            self.courserun_key,
            self.enterprise_customer_uuid,
        )
        assert response.get('successes') == [{'email': self.user_email, 'course_run_key': self.courserun_key}]
        mock_oauth_client().post.assert_called_with(
            os.path.join(EnterpriseApiClient.enterprise_customer_endpoint, str(self.enterprise_customer_uuid)) +
            '/enroll_learners_in_courses/',
            json={'enrollments_info': [{
                'email': self.user_email,
                'course_run_key': self.courserun_key,
                'transaction_id': 'some-transaction-id',
            }]},
            timeout=settings.BULK_ENROLL_REQUEST_TIMEOUT_SECONDS
        )

    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_successful_fetch_enterprise_data(self, mock_oauth_client):
        """
        Test the enterprise client's ability to handle successful api requests to fetch information on an enterprise
        customer
        """
        mock_oauth_client.return_value.get.return_value = MockResponse(
            {
                "uuid": str(self.enterprise_customer_uuid),
                "name": "The Whinery Spirits Company",
                "slug": "the-whinery-spirits-company",
                "active": True,
                "enterprise_customer_catalogs": [
                    "af67a92c-acbe-400a-93af-42074abc70b0"
                ],
                "modified": "2023-02-08T15:40:29.092448Z",
                "admin_users": [
                    {
                        "email": "enterprise_admin_the-whinery-spirits-company@example.com",
                        "lms_user_id": 14
                    },
                    {
                        "email": "aballplayer@gmail.com",
                        "lms_user_id": 33
                    }
                ]
            },
            201,
        )

        enterprise_client = EnterpriseApiClient()
        response = enterprise_client.get_enterprise_customer_data(self.enterprise_customer_uuid)
        assert response.get('uuid') == str(self.enterprise_customer_uuid)
