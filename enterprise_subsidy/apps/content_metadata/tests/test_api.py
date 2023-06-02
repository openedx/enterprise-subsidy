"""
Tests for the ContentMetadataApi class.
"""
from unittest import mock
from uuid import uuid4

import ddt
from django.test import TestCase
from edx_django_utils.cache import TieredCache

from enterprise_subsidy.apps.subsidy.constants import CENTS_PER_DOLLAR

from ..api import ContentMetadataApi, content_metadata_cache_key
from ..constants import CourseModes, ProductSources


@ddt.ddt
class ContentMetadataApiTests(TestCase):
    """
    Tests for the content metadata api.
    """
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.content_metadata_api = ContentMetadataApi()
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

    @ddt.data(
        {
            'entitlements': [
                {
                    "mode": "paid-executive-education",
                    "price": "2100.00",
                    "currency": "USD",
                    "sku": "B98DE21",
                }
            ],
            'product_source': {
                "name": "2u",
                "slug": "2u",
                "description": "2U, Trilogy, Getsmarter -- external source for 2u courses and programs"
            },
        },
        {
            'entitlements': [
                {
                    "mode": "verified",
                    "price": "794.00",
                    "currency": "USD",
                    "sku": "B6DE08E",
                }
            ],
            'product_source': None,
        },
    )
    @ddt.unpack
    @mock.patch('enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_metadata')
    def test_client_can_fetch_mode_specific_prices(
        self,
        mock_get_content_metadata,
        entitlements,
        product_source,
    ):
        """
        Test the enterprise catalog client's ability to handle api requests to fetch content metadata from the catalog
        service and return formatted pricing data on the content based on content mode.
        """
        mocked_data = self.course_metadata.copy()
        mocked_data['product_source'] = product_source
        mocked_data['entitlements'] = entitlements
        mock_get_content_metadata.return_value = mocked_data
        price_in_cents = self.content_metadata_api.get_course_price(
            self.enterprise_customer_uuid, self.course_key
        )
        assert price_in_cents == float(entitlements[0].get('price')) * CENTS_PER_DOLLAR

    @ddt.data(
        {
            "name": "2u",
            "slug": "2u",
            "description": "2U, Trilogy, Getsmarter -- external source for 2u courses and programs"
        },
        None
    )
    @mock.patch('enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_metadata')
    def test_client_discern_product_source(self, product_source, mock_get_content_metadata):
        """
        Test that the catalog client has the ability to smartly return the product source value from the content
        metadata payload
        """
        mocked_data = self.course_metadata.copy()
        mocked_data['product_source'] = product_source
        mock_get_content_metadata.return_value = mocked_data
        response = self.content_metadata_api.get_product_source(
            self.enterprise_customer_uuid, self.course_key
        )
        source_name = product_source.get('name') if product_source else 'edX'
        expected_source = source_name if product_source else ProductSources.EDX.value
        assert expected_source == response

    def test_summary_data_for_content(self):
        summary = self.content_metadata_api.summary_data_for_content(self.courserun_key, self.course_metadata)
        assert summary.get('content_key') == self.course_key
        assert summary.get('course_run_key') == self.courserun_key
        assert summary.get('content_price') == 14900

    def test_summary_data_for_exec_ed_content(self):
        executive_education_course_metadata = {
            "key": self.course_key,
            "content_type": "course",
            "uuid": str(uuid4()),
            "title": "Demonstration Course",
            "entitlements": [
                {
                    "mode": "paid-executive-education",
                    "price": "599.49",
                    "currency": "USD",
                    "sku": "B98DE21",
                    "expires": "null"
                }
            ],
            "product_source": {
                "name": "2u",
                "slug": "2u",
                "description": "2U, Trilogy, Getsmarter -- external source for 2u courses and programs"
            },
            "additional_metadata": {
                "variant_id": "79a95406-a9ac-49b3-a27c-44f3fd06092e"
            }
        }
        mode = self.content_metadata_api.mode_for_content(executive_education_course_metadata)
        assert mode == 'paid-executive-education'
        summary = self.content_metadata_api.summary_data_for_content(
            self.course_key,
            executive_education_course_metadata
        )
        assert summary.get('content_key') == self.course_key
        assert summary.get('course_run_key') is None
        assert summary.get('content_price') == 59949

    @ddt.data(
        {
            'content_data': {},
            'course_run_data': {'first_enrollable_paid_seat_price': '100.00'},
            'expected_price': 10000,
        },
        {
            'content_data': {
                'product_source': {'name': ProductSources.EDX.value, 'slug': ProductSources.EDX.value},
                'entitlements': [{'mode': CourseModes.EDX_VERIFIED.value, 'price': '3.50'}],
            },
            'course_run_data': {},
            'expected_price': 350,
        },
        {
            'content_data': {
                'product_source': {'name': ProductSources.TWOU.value, 'slug': ProductSources.TWOU.value},
                'entitlements': [{'mode': CourseModes.EXECUTIVE_EDUCATION.value, 'price': '4.20'}],
            },
            'course_run_data': {},
            'expected_price': 420,
        },
        {
            'content_data': {},
            'course_run_data': {},
            'expected_price': None,
        },
    )
    @ddt.unpack
    def test_price_for_content(self, content_data, course_run_data, expected_price):
        actual_price = self.content_metadata_api.price_for_content(content_data, course_run_data)
        self.assertEqual(expected_price, actual_price)

    @mock.patch('enterprise_subsidy.apps.content_metadata.api.EnterpriseCatalogApiClient')
    def test_tiered_caching_works(self, mock_catalog_client):
        """
        Tests that consecutive calls for the same content metadata
        within the same request utilize the cache.
        """
        cache_key = content_metadata_cache_key(self.enterprise_customer_uuid, self.course_key)
        self.assertFalse(TieredCache.get_cached_response(cache_key).is_found)
        client_instance = mock_catalog_client.return_value
        client_instance.get_content_metadata_for_customer.return_value = {'the': 'metadata'}

        _ = ContentMetadataApi.get_content_metadata(self.enterprise_customer_uuid, self.course_key)

        self.assertTrue(TieredCache.get_cached_response(cache_key).is_found)
        self.assertEqual(
            TieredCache.get_cached_response(cache_key).value,
            {'the': 'metadata'},
        )
        self.assertEqual(
            ContentMetadataApi.get_content_metadata(self.enterprise_customer_uuid, self.course_key),
            {'the': 'metadata'},
        )
        TieredCache.delete_all_tiers(cache_key)
