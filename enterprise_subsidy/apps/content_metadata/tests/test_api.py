"""
Tests for the ContentMetadataApi class.
"""
from unittest import mock
from uuid import uuid4

import ddt
from django.test import TestCase
from edx_django_utils.cache import TieredCache

from ..api import ContentMetadataApi, content_metadata_cache_key, content_metadata_for_customer_cache_key
from ..constants import DEFAULT_CONTENT_PRICE, CourseModes, ProductSources


@ddt.ddt
class ContentMetadataApiTests(TestCase):
    """
    Tests for the content metadata api.
    """
    course_key = 'edX+DemoX'
    courserun_key_1 = 'course-v1:edX+DemoX+Demo_Course.1'
    courserun_key_2 = 'course-v1:edX+DemoX+Demo_Course.2'
    variant_id_1 = str(uuid4())
    variant_id_2 = str(uuid4())

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.content_metadata_api = ContentMetadataApi()
        cls.enterprise_customer_uuid = uuid4()
        cls.user_id = 3
        cls.user_email = 'ayy@lmao.com'
        cls.course_uuid = uuid4()
        cls.courserun_uuid_1 = uuid4()
        cls.courserun_uuid_2 = uuid4()

        cls.course_entitlements = [
            {'mode': 'verified', 'price': '149.00', 'currency': 'USD', 'sku': '8A47F9E', 'expires': 'null'}
        ]
        cls.course_metadata = {
            'key': cls.course_key,
            'content_type': 'course',
            'uuid': cls.course_uuid,
            'title': 'Demonstration Course',
            'course_runs': [{
                'key': cls.courserun_key_1,
                'uuid': str(cls.courserun_uuid_1),
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
            'course_run_keys': [cls.courserun_key_1],
            'content_last_modified': '2023-03-06T20:56:46.003840Z',
            'enrollment_url': 'https://foobar.com',
            'active': False,
            'normalized_metadata': {
                'enroll_by_date': '2023-05-26T15:45:32.494051Z',
            },
            "normalized_metadata_by_run": {
                "course-v1:edX+DemoX+Demo_Course.1": {
                    "content_price": 149.0
                }
            }
        }

        cls.executive_education_course_metadata = {
            "key": cls.course_key,
            "content_type": "course",
            "uuid": cls.course_uuid,
            "title": "Demonstration Exec Ed Course",
            "course_runs": [
                {
                    "key": cls.courserun_key_1,
                    "uuid": str(cls.courserun_uuid_1),
                    "title": "Demonstration Exec Ed Course",
                    "variant_id": cls.variant_id_1,
                    "enrollment_end": "2023-06-24T00:00:00.000000Z",
                },
                {
                    "key": cls.courserun_key_2,
                    "uuid": str(cls.courserun_uuid_2),
                    "title": "Demonstration Exec Ed Course",
                    "variant_id": cls.variant_id_2,
                    "enrollment_end": "2024-06-24T00:00:00.000000Z",
                },
            ],
            "course_run_keys": [
                cls.courserun_key_1,
                cls.courserun_key_2,
            ],
            "advertised_course_run_uuid": str(cls.courserun_uuid_2),
            "entitlements": [
                {
                    "mode": "paid-executive-education",
                    "price": "599.49",
                    "currency": "USD",
                    "sku": "B98DE21",
                    "expires": "null",
                }
            ],
            "product_source": {
                "name": "2u",
                "slug": "2u",
                "description": "2U, Trilogy, Getsmarter -- external source for 2u courses and programs",
            },
            "additional_metadata": {
                "variant_id": cls.variant_id_2,
            },
            "normalized_metadata_by_run": {
                "course-v1:edX+DemoX+Demo_Course.1": {
                    "content_price": 599.49
                },
                "course-v1:edX+DemoX+Demo_Course.2": {
                    "content_price": 599.49
                }
            }
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
            'course_runs': [],
            'expected_price': 210000,
            'advertised_course_run_uuid': None,
        },
        {
            'course_runs': [
                {
                    'uuid': '1234',
                    'first_enrollable_paid_seat_price': '123.50',
                }
            ],
            'advertised_course_run_uuid': '1234',
            'entitlements': None,
            'product_source': None,
            'expected_price': 12350,
        },
    )
    @ddt.unpack
    @mock.patch('enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_metadata_for_customer')
    def test_client_can_fetch_mode_specific_prices(
        self,
        mock_get_content_metadata,
        entitlements,
        product_source,
        course_runs,
        expected_price,
        advertised_course_run_uuid,
    ):
        """
        Test the enterprise catalog client's ability to handle api requests to fetch content metadata from the catalog
        service and return formatted pricing data on the content based on content mode.
        """
        mocked_data = self.course_metadata.copy()
        mocked_data['product_source'] = product_source
        mocked_data['entitlements'] = entitlements
        mocked_data['course_runs'] = course_runs
        mocked_data['advertised_course_run_uuid'] = advertised_course_run_uuid
        mock_get_content_metadata.return_value = mocked_data
        price_in_cents = self.content_metadata_api.get_course_price(
            self.enterprise_customer_uuid, self.course_key
        )
        assert price_in_cents == expected_price

    @ddt.data(
        {
            "name": "2u",
            "slug": "2u",
            "description": "2U, Trilogy, Getsmarter -- external source for 2u courses and programs"
        },
        None
    )
    @mock.patch('enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_metadata_for_customer')
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
        summary = self.content_metadata_api.summary_data_for_content(self.courserun_key_1, self.course_metadata)
        assert summary.get('content_key') == self.course_key
        assert summary.get('course_run_key') == self.courserun_key_1
        assert summary.get('content_price') == 14900
        assert summary.get('enroll_by_date') == '2023-05-26T15:45:32.494051Z'

    def test_summary_data_for_exec_ed_content(self):
        mode = self.content_metadata_api.mode_for_content(self.executive_education_course_metadata)
        assert mode == 'paid-executive-education'

        # Test assembling summary data given an identifier of a course.
        summary = self.content_metadata_api.summary_data_for_content(
            self.course_key,
            self.executive_education_course_metadata,
        )
        assert summary.get('content_key') == self.course_key
        assert summary.get('course_run_key') is self.courserun_key_2
        assert summary.get('content_price') == 59949
        assert summary.get('geag_variant_id') == self.variant_id_2

        # Test assembling summary data given an identifier of a non-advertised course run.
        summary = self.content_metadata_api.summary_data_for_content(
            self.courserun_key_1,
            self.executive_education_course_metadata,
        )
        assert summary.get('content_key') == self.course_key
        assert summary.get('course_run_key') is self.courserun_key_1
        assert summary.get('content_price') == 59949
        assert summary.get('geag_variant_id') == self.variant_id_1
        assert summary.get('enroll_by_date') == '2023-06-24T00:00:00.000000Z'

        # Test assembling summary data given an identifier of an advertised course run.
        # Note, the result should be identical to when a course identifier is given.
        summary = self.content_metadata_api.summary_data_for_content(
            self.courserun_key_2,
            self.executive_education_course_metadata,
        )
        assert summary.get('content_key') == self.course_key
        assert summary.get('course_run_key') is self.courserun_key_2
        assert summary.get('content_price') == 59949
        assert summary.get('geag_variant_id') == self.variant_id_2
        assert summary.get('enroll_by_date') == '2024-06-24T00:00:00.000000Z'

    @ddt.data(
        {
            'remove_variant_id_from_runs': False,
            'remove_variant_id_from_additional_metadata': True,
            'requested_content_key': course_key,
            'expected_variant_id': variant_id_2,  # The variant from the advertised run should be selected.
        },
        {
            'remove_variant_id_from_runs': True,
            'remove_variant_id_from_additional_metadata': True,
            'requested_content_key': course_key,
            'expected_variant_id': None,
        },
        {
            'remove_variant_id_from_runs': False,
            'remove_variant_id_from_additional_metadata': True,
            'requested_content_key': courserun_key_1,
            'expected_variant_id': variant_id_1,
        },
        {
            'remove_variant_id_from_runs': True,
            'remove_variant_id_from_additional_metadata': True,
            'requested_content_key': courserun_key_1,
            'expected_variant_id': None,
        },
        {
            'remove_variant_id_from_runs': False,
            'remove_variant_id_from_additional_metadata': True,
            'requested_content_key': courserun_key_2,
            'expected_variant_id': variant_id_2,
        },
        {
            'remove_variant_id_from_runs': True,
            'remove_variant_id_from_additional_metadata': True,
            'requested_content_key': courserun_key_2,
            'expected_variant_id': None,
        },
        # We can remove all the following test cases once we stop populating the
        # deprecated ``additional_metadata``.
        {
            'remove_variant_id_from_runs': False,
            'remove_variant_id_from_additional_metadata': False,
            'requested_content_key': course_key,
            'expected_variant_id': variant_id_2,  # The variant from the advertised run should be selected.
        },
        {
            'remove_variant_id_from_runs': True,
            'remove_variant_id_from_additional_metadata': False,
            'requested_content_key': course_key,
            'expected_variant_id': None,
        },
        {
            'remove_variant_id_from_runs': False,
            'remove_variant_id_from_additional_metadata': False,
            'requested_content_key': courserun_key_1,
            'expected_variant_id': variant_id_1,
        },
        {
            'remove_variant_id_from_runs': True,
            'remove_variant_id_from_additional_metadata': False,
            'requested_content_key': courserun_key_1,
            'expected_variant_id': None,
        },
        {
            'remove_variant_id_from_runs': False,
            'remove_variant_id_from_additional_metadata': False,
            'requested_content_key': courserun_key_2,
            'expected_variant_id': variant_id_2,
        },
        {
            'remove_variant_id_from_runs': True,
            'remove_variant_id_from_additional_metadata': False,
            'requested_content_key': courserun_key_2,
            'expected_variant_id': None,
        },
    )
    @ddt.unpack
    def test_summary_data_for_exec_ed_content_variant_id_sometimes_missing(
        self,
        remove_variant_id_from_runs,
        remove_variant_id_from_additional_metadata,
        requested_content_key,
        expected_variant_id,
    ):
        """
        Test which variant_id is returned in summary data depending on a couple situations:
        - whether variant_id is present in runs (such as with OCM content), and
        - which content key was requested (course vs. advertised run vs.  non-advertised run).
        """
        mocked_data = self.executive_education_course_metadata.copy()
        if remove_variant_id_from_runs:
            for run in mocked_data['course_runs']:
                del run['variant_id']
        if remove_variant_id_from_additional_metadata:
            del mocked_data['additional_metadata']['variant_id']

        summary = self.content_metadata_api.summary_data_for_content(
            requested_content_key,
            mocked_data,
        )
        assert summary.get('geag_variant_id') == expected_variant_id

    @ddt.data(
        {
            'content_data': {},
            'course_run_data': {'first_enrollable_paid_seat_price': '100.00'},
            'expected_price': 10000,
        },
        {
            'content_data': {
                'product_source': {'name': ProductSources.EDX.value, 'slug': ProductSources.EDX.value},
                'entitlements': [{'mode': CourseModes.EDX_VERIFIED.value, 'price': '34.50'}],
            },
            'course_run_data': {'first_enrollable_paid_seat_price': '3.50'},
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
            'expected_price': DEFAULT_CONTENT_PRICE,
        },
        {
            'content_data': {},
            'course_run_data': {'first_enrollable_paid_seat_price': None},
            'expected_price': DEFAULT_CONTENT_PRICE,
        },
    )
    @ddt.unpack
    def test_price_for_content(self, content_data, course_run_data, expected_price):
        actual_price = self.content_metadata_api.price_for_content(content_data, course_run_data)
        self.assertEqual(expected_price, actual_price)

    @mock.patch('enterprise_subsidy.apps.content_metadata.api.EnterpriseCatalogApiClientV2')
    @mock.patch('enterprise_subsidy.apps.content_metadata.api.EnterpriseCatalogApiClient')
    def test_tiered_caching_works(self, mock_catalog_client_v1, mock_catalog_client_v2):
        """
        Tests that consecutive calls for the same content metadata
        within the same request utilize the cache.
        """
        cache_key = content_metadata_for_customer_cache_key(self.enterprise_customer_uuid, self.course_key)
        self.assertFalse(TieredCache.get_cached_response(cache_key).is_found)
        client_instance_v1 = mock_catalog_client_v1.return_value
        client_instance_v2 = mock_catalog_client_v2.return_value
        client_instance_v2.get_content_metadata_for_customer.return_value = {'the': 'metadata'}

        _ = ContentMetadataApi.get_content_metadata_for_customer(self.enterprise_customer_uuid, self.course_key)

        self.assertTrue(TieredCache.get_cached_response(cache_key).is_found)
        self.assertEqual(
            TieredCache.get_cached_response(cache_key).value,
            {'the': 'metadata'},
        )
        self.assertEqual(
            ContentMetadataApi.get_content_metadata_for_customer(self.enterprise_customer_uuid, self.course_key),
            {'the': 'metadata'},
        )
        TieredCache.delete_all_tiers(cache_key)

        cache_key = content_metadata_cache_key(self.course_key)
        self.assertFalse(TieredCache.get_cached_response(cache_key).is_found)
        client_instance_v1.get_content_metadata.return_value = {'the': 'metadata'}

        _ = ContentMetadataApi.get_content_metadata(self.course_key)

        self.assertTrue(TieredCache.get_cached_response(cache_key).is_found)
        self.assertEqual(
            TieredCache.get_cached_response(cache_key).value,
            {'the': 'metadata'},
        )
        self.assertEqual(
            ContentMetadataApi.get_content_metadata(self.course_key),
            {'the': 'metadata'},
        )
        assert client_instance_v1.get_content_metadata.call_count == 1
        TieredCache.delete_all_tiers(cache_key)

    @ddt.data(True, False)
    def test_enroll_by_date_for_verified_course_run_content(self, has_override):
        upgrade_deadline_key = 'upgrade_deadline_override' if has_override else 'upgrade_deadline'
        content_data = {
            'content_type': 'courserun',
            'enrollment_end': '2024-12-01T00:00:00Z',
            'seats': [
                {
                    'type': 'verified',
                    upgrade_deadline_key: '2025-01-01T00:00:00Z',
                }
            ]
        }
        self.assertEqual(
            ContentMetadataApi().enroll_by_date_for_content(content_data, 'verified'),
            '2025-01-01T00:00:00Z',
        )

    @ddt.data('verified', 'paid-executive-education')
    def test_enroll_by_date_for_content_fallback(self, mode):
        content_data = {
            'content_type': 'courserun',
            'enrollment_end': '2024-12-01T00:00:00Z',
        }
        self.assertEqual(
            ContentMetadataApi().enroll_by_date_for_content(content_data, mode),
            '2024-12-01T00:00:00Z',
        )

    def test_enroll_by_date_for_content_handles_null(self):
        content_data = {
            'content_type': 'courserun',
        }
        self.assertIsNone(ContentMetadataApi().enroll_by_date_for_content(content_data, 'verified'))
