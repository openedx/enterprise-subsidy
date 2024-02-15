from unittest import mock
from uuid import uuid4

import ddt
from django.test import TestCase

from enterprise_subsidy.apps.api_client.enterprise_catalog import EnterpriseCatalogApiClient
from test_utils.utils import MockResponse


@ddt.ddt
class EnterpriseCatalogApiClientTests(TestCase):
    """
    Tests for the enterprise catalog api client.
    """
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.enterprise_customer_uuid = uuid4()
        cls.user_id = 3
        cls.user_email = 'ayy@lmao.com'
        cls.course_key = 'edX+DemoX'
        cls.course_uuid = uuid4()
        cls.courserun_key = 'course-v1:edX+DemoX+Demo_Course'

        cls.course_entitlements = [
            {'mode': 'verified', 'price': '149.00', 'currency': 'USD', 'sku': '8A47F9E', 'expires': 'null'}
        ]
        cls.course_metadata = {
            'key': cls.course_key,
            'content_type': 'course',
            'uuid': cls.course_uuid,
            'title': 'Demonstration Course',
            'course_runs': [{
                'key': cls.courserun_key,
                'uuid': '00f8945b-bb50-4c7a-98f4-2f2f6178ff2f',
                'title': 'Demonstration Course',
                'external_key': None,
                'seats': [{
                    'type': 'verified',
                    'price': '149.00',
                    'currency': 'USD',
                    'upgrade_deadline': '2023-05-26T15:45:32.494051Z',
                    'upgrade_deadline_override': None,
                    'credit_provider': None,
                    'credit_hours': None,
                    'sku': '8CF08E5',
                    'bulk_sku': 'A5B6DBE'
                }, {
                    'type': 'audit',
                    'price': '0.00',
                    'currency': 'USD',
                    'upgrade_deadline': None,
                    'upgrade_deadline_override': None,
                    'credit_provider': None,
                    'credit_hours': None,
                    'sku': '68EFFFF',
                    'bulk_sku': None
                }],
                'start': '2013-02-05T05:00:00Z',
                'end': None,
                'go_live_date': None,
                'enrollment_start': None,
                'enrollment_end': None,
                'is_enrollable': True,
                'availability': 'Current',
                'course': 'edX+DemoX',
                'first_enrollable_paid_seat_price': 149,
                'enrollment_count': 0,
                'recent_enrollment_count': 0,
                'course_uuid': cls.course_uuid,
            }],
            'entitlements': cls.course_entitlements,
            'modified': '2022-05-26T15:46:24.355321Z',
            'additional_metadata': None,
            'enrollment_count': 0,
            'recent_enrollment_count': 0,
            'course_run_keys': [cls.courserun_key],
            'content_last_modified': '2023-03-06T20:56:46.003840Z',
            'enrollment_url': 'https://foobar.com',
            'active': False
        }

    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_successful_fetch_course_content_metadata_for_customer(self, mock_oauth_client):
        """
        Test the enterprise catalog client's ability to handle api requests to fetch customer specific content metadata
        from the catalog service.
        """
        mock_oauth_client.return_value.get.return_value = MockResponse(self.course_metadata, 200)
        enterprise_catalog_client = EnterpriseCatalogApiClient()
        response = enterprise_catalog_client.get_content_metadata_for_customer(
            self.enterprise_customer_uuid, self.course_key
        )
        assert response == self.course_metadata

    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_successful_fetch_course_content_metadata(self, mock_oauth_client):
        """
        Test the enterprise catalog client's ability to handle api requests to fetch content metadata from the catalog
        service.
        """
        mock_oauth_client.return_value.get.return_value = MockResponse(
            {
                'results': [self.course_metadata],
                'count': 1,
                'next': None,
                'previous': None,
            },
            200,
        )
        enterprise_catalog_client = EnterpriseCatalogApiClient()
        response = enterprise_catalog_client.get_content_metadata(self.course_key)
        assert response == self.course_metadata
        assert mock_oauth_client.return_value.get.call_args.args[0] == enterprise_catalog_client.metadata_endpoint
        assert mock_oauth_client.return_value.get.call_args.kwargs == {'params': {'content_identifiers': ['edX+DemoX']}}
