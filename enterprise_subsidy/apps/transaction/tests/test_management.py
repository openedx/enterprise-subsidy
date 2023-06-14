"""
Test the Enterprise Subsidy service management commands and related functions.
"""

import uuid
from unittest import TestCase, mock

import ddt
from django.core.management import call_command
from openedx_ledger.models import Reversal
from openedx_ledger.test_utils.factories import LedgerFactory, ReversalFactory, TransactionFactory
from pytest import mark

from enterprise_subsidy.apps.subsidy.tests.factories import SubsidyFactory
from test_utils.utils import MockResponse


@mark.django_db
@ddt.ddt
class TestTransactionManagementCommand(TestCase):
    """
    Test the Enterprise Subsidy service management commands and related functions.
    """

    def setUp(self):
        super().setUp()

        self.course_key = 'edX+DemoX'
        self.course_uuid = uuid.uuid4()
        self.courserun_key = 'course-v1:edX+DemoX+Demo_Course'
        self.course_entitlements = [
            {'mode': 'verified', 'price': '149.00', 'currency': 'USD', 'sku': '8A47F9E', 'expires': 'null'}
        ]

        self.ledger = LedgerFactory()
        self.subsidy = SubsidyFactory(ledger=self.ledger)
        self.fulfillment_identifier = str(uuid.uuid4())
        self.transaction = TransactionFactory(
            ledger=self.ledger,
            quantity=100,
            fulfillment_identifier=self.fulfillment_identifier
        )

    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_write_reversals_from_enterprise_unenrollment_with_existing_reversal(self, mock_oauth_client):
        """
        Test that the write_reversals_from_enterprise_unenrollments management command does not create a reversal if
        one already exists.
        """
        unenrolled_at = '2023-06-1T19:27:29Z'
        mock_oauth_client.return_value.get.return_value = MockResponse(
            [{
                'enterprise_course_enrollment': {
                    'enterprise_customer_user': 10,
                    'course_id': self.courserun_key,
                    'created': '2023-05-25T19:27:29Z',
                    'unenrolled_at': unenrolled_at,
                },
                'transaction_id': self.transaction.uuid,
                'uuid': self.fulfillment_identifier,
            }],
            200
        )
        ReversalFactory(
            transaction=self.transaction,
            idempotency_key=f'unenrollment-reversal-{self.fulfillment_identifier}-{unenrolled_at}'
        )
        assert Reversal.objects.count() == 1
        call_command('write_reversals_from_enterprise_unenrollments')
        assert Reversal.objects.count() == 1

    @mock.patch(
        'enterprise_subsidy.apps.transaction.management.commands.write_reversals_from_enterprise_unenrollments.'
        'EnterpriseApiClient'
    )
    @mock.patch(
        'enterprise_subsidy.apps.transaction.management.commands.write_reversals_from_enterprise_unenrollments.'
        'ContentMetadataApi'
    )
    @mock.patch(
        'enterprise_subsidy.apps.transaction.signals.handlers.EnterpriseApiClient'
    )
    def test_write_reversals_from_enterprise_unenrollments_with_microsecond_datetime_strings(
        self,
        mock_signal_client,
        mock_fetch_course_metadata_client,
        mock_fetch_recent_unenrollments_client,
    ):
        mock_signal_client.return_value = mock.MagicMock()
        transaction_uuid_2 = uuid.uuid4()
        TransactionFactory(
            ledger=self.ledger,
            quantity=100,
            uuid=transaction_uuid_2,
            fulfillment_identifier=str(uuid.uuid4()),
        )
        mock_fetch_recent_unenrollments_client.return_value.fetch_recent_unenrollments.return_value = [
            {
                'enterprise_course_enrollment': {
                    'enterprise_customer_user': 10,
                    'course_id': self.transaction.content_key,
                    # Created at and unenrolled_at both have microseconds as part of the datetime string
                    'created': '2023-05-25T19:27:29.182347Z',
                    'unenrolled_at': '2023-06-1T19:27:29.12939Z',
                },
                'transaction_id': self.transaction.uuid,
                'uuid': str(self.transaction.fulfillment_identifier),
            },
        ]

        mock_fetch_course_metadata_client.get_content_metadata.return_value = {
            'key': self.course_key,
            'content_type': 'course',
            'uuid': self.course_uuid,
            'title': 'Demonstration Course',
            'course_runs': [{
                'key': self.transaction.content_key,
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
                # Courserun start date has microseconds as part of the datetime string
                'start': '2013-02-05T05:00:00.355321Z',
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
                'course_uuid': self.course_uuid,
            }],
            'entitlements': self.course_entitlements,
            'modified': '2022-05-26T15:46:24.355321Z',
            'additional_metadata': None,
            'enrollment_count': 0,
            'recent_enrollment_count': 0,
            'course_run_keys': [self.courserun_key],
            'content_last_modified': '2023-03-06T20:56:46Z',
            'enrollment_url': 'https://foobar.com',
            'active': False
        }

        call_command('write_reversals_from_enterprise_unenrollments')
        # Really all we need to assert here is that the command does not raise an exception while parsing the datetime
        # strings
        assert mock_fetch_course_metadata_client.get_content_metadata.call_count == 1

    @mock.patch(
        'enterprise_subsidy.apps.transaction.management.commands.write_reversals_from_enterprise_unenrollments.'
        'EnterpriseApiClient'
    )
    @mock.patch(
        'enterprise_subsidy.apps.transaction.management.commands.write_reversals_from_enterprise_unenrollments.'
        'ContentMetadataApi'
    )
    @mock.patch(
        'enterprise_subsidy.apps.transaction.signals.handlers.EnterpriseApiClient'
    )
    def test_write_reversals_from_enterprise_unenrollment_does_not_rerequest_metadata(
        self,
        mock_signal_client,
        mock_fetch_course_metadata_client,
        mock_fetch_recent_unenrollments_client,
    ):
        """
        Test that the write_reversals_from_enterprise_unenrollments management command does not re-request metadata
        from the catalog service if it has already been requested.
        """
        # Reversal creation will trigger a signal handler that will make a call to enterprise
        mock_signal_client.return_value = mock.MagicMock()

        transaction_uuid_2 = uuid.uuid4()
        TransactionFactory(
            ledger=self.ledger,
            quantity=100,
            uuid=transaction_uuid_2,
            fulfillment_identifier=str(uuid.uuid4()),
        )
        mock_fetch_recent_unenrollments_client.return_value.fetch_recent_unenrollments.return_value = [
            {
                'enterprise_course_enrollment': {
                    'enterprise_customer_user': 10,
                    'course_id': self.transaction.content_key,
                    'created': '2023-05-25T19:27:29Z',
                    'unenrolled_at': '2023-06-1T19:27:29Z',
                },
                'transaction_id': self.transaction.uuid,
                'uuid': str(self.transaction.fulfillment_identifier),
            },
            {
                'enterprise_course_enrollment': {
                    'enterprise_customer_user': 11,
                    'course_id': self.transaction.content_key,
                    'created': '2023-05-25T19:27:29Z',
                    'unenrolled_at': '2023-06-1T19:27:29Z',
                },
                'transaction_id': transaction_uuid_2,
                'uuid': str(uuid.uuid4()),
            }
        ]

        mock_fetch_course_metadata_client.get_content_metadata.return_value = {
            'key': self.course_key,
            'content_type': 'course',
            'uuid': self.course_uuid,
            'title': 'Demonstration Course',
            'course_runs': [{
                'key': self.transaction.content_key,
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
                'course_uuid': self.course_uuid,
            }],
            'entitlements': self.course_entitlements,
            'modified': '2022-05-26T15:46:24.355321Z',
            'additional_metadata': None,
            'enrollment_count': 0,
            'recent_enrollment_count': 0,
            'course_run_keys': [self.courserun_key],
            'content_last_modified': '2023-03-06T20:56:46Z',
            'enrollment_url': 'https://foobar.com',
            'active': False
        }

        call_command('write_reversals_from_enterprise_unenrollments')
        # Assert that we only make two calls with the oauth client, one to the enterprise service to fetch
        # unenrollments and only one to the catalog service to fetch course metadata
        assert mock_fetch_course_metadata_client.get_content_metadata.call_count == 1
        assert mock_fetch_recent_unenrollments_client.return_value.fetch_recent_unenrollments.call_count == 1

    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_write_reversals_from_enterprise_unenrollment_transaction_does_not_exist(self, mock_oauth_client):
        """
        Test that the write_reversals_from_enterprise_unenrollments management command does not create a reversal if
        the transaction does not exist.
        """
        mock_oauth_client.return_value.get.return_value = MockResponse(
            [{
                'enterprise_course_enrollment': {
                    'enterprise_customer_user': 10,
                    'course_id': self.courserun_key,
                    'created': '2023-05-25T19:27:29Z',
                    'unenrolled_at': '2023-06-1T19:27:29Z',
                },
                'transaction_id': uuid.uuid4(),
                'uuid': self.fulfillment_identifier,
            }],
            200
        )
        assert Reversal.objects.count() == 0
        call_command('write_reversals_from_enterprise_unenrollments')
        assert Reversal.objects.count() == 0

    @mock.patch(
        'enterprise_subsidy.apps.transaction.management.commands.write_reversals_from_enterprise_unenrollments.'
        'EnterpriseApiClient'
    )
    @mock.patch(
        'enterprise_subsidy.apps.transaction.management.commands.write_reversals_from_enterprise_unenrollments.'
        'ContentMetadataApi'
    )
    @mock.patch(
        'enterprise_subsidy.apps.transaction.signals.handlers.EnterpriseApiClient'
    )
    @ddt.data(
        ('2023-05-25T19:27:29Z', '2023-06-1T19:27:29Z'),
        ('2023-06-1T19:27:29Z', '2023-05-25T19:27:29Z'),
    )
    @ddt.unpack
    def test_write_reversals_from_enterprise_unenrollment_refund_period_ended(
        self,
        course_start_date,
        enrollment_created_at,
        mock_signal_client,
        mock_fetch_course_metadata_client,
        mock_fetch_recent_unenrollments_client,
    ):
        """
        Test that for write_reversals_from_enterprise_unenrollments, if the greater date between the course start date
        and the enrollment created at date is more than 14 days before the unenrollment date, no reversal is created.
        """
        # Reversal creation will trigger a signal handler that will make a call to enterprise
        mock_signal_client.return_value = mock.MagicMock()
        # unenrolled_at is 14 days after the considered refund period start date so the reversal is not created
        unenrolled_at = '2023-06-16T19:27:29Z'

        # Call to enterprise, fetching recent unenrollments
        mock_fetch_recent_unenrollments_client.return_value.fetch_recent_unenrollments.return_value = [
            {
                'enterprise_course_enrollment': {
                    'enterprise_customer_user': 10,
                    'course_id': self.transaction.content_key,

                    'created': enrollment_created_at,
                    'unenrolled_at': unenrolled_at,
                },
                'transaction_id': self.transaction.uuid,
                'uuid': str(self.transaction.fulfillment_identifier),
            }
        ]

        # Call to enterprise catalog, fetching course metadata
        mock_fetch_course_metadata_client.get_content_metadata.return_value = {
            'key': self.course_key,
            'content_type': 'course',
            'uuid': self.course_uuid,
            'title': 'Demonstration Course',
            'course_runs': [{
                'key': self.transaction.content_key,
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
                'start': course_start_date,
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
                'course_uuid': self.course_uuid,
            }],
            'entitlements': self.course_entitlements,
            'modified': '2022-05-26T15:46:24.355321Z',
            'additional_metadata': None,
            'enrollment_count': 0,
            'recent_enrollment_count': 0,
            'course_run_keys': [self.courserun_key],
            'content_last_modified': '2023-03-06T20:56:46Z',
            'enrollment_url': 'https://foobar.com',
            'active': False
        }

        assert Reversal.objects.count() == 0
        call_command('write_reversals_from_enterprise_unenrollments')
        assert Reversal.objects.count() == 0

    @mock.patch(
        'enterprise_subsidy.apps.transaction.management.commands.write_reversals_from_enterprise_unenrollments.'
        'EnterpriseApiClient'
    )
    @mock.patch(
        'enterprise_subsidy.apps.transaction.management.commands.write_reversals_from_enterprise_unenrollments.'
        'ContentMetadataApi'
    )
    @mock.patch(
        'enterprise_subsidy.apps.transaction.signals.handlers.EnterpriseApiClient'
    )
    @ddt.data(True, False)
    def test_write_reversals_from_enterprise_unenrollments(
        self,
        dry_run_enabled,
        mock_signal_client,
        mock_fetch_course_metadata_client,
        mock_fetch_recent_unenrollments_client,
    ):
        """
        Test the write_reversals_from_enterprise_unenrollments management command's ability to create a reversal.
        """
        # Reversal creation will trigger a signal handler that will make a call to enterprise
        mock_signal_client.return_value = mock.MagicMock()

        # Call to enterprise, fetching recent unenrollments
        mock_fetch_recent_unenrollments_client.return_value.fetch_recent_unenrollments.return_value = [
            {
                'enterprise_course_enrollment': {
                    'enterprise_customer_user': 10,
                    'course_id': self.transaction.content_key,
                    'created': '2023-05-25T19:27:29Z',
                    'unenrolled_at': '2023-06-1T19:27:29Z',
                },
                'transaction_id': self.transaction.uuid,
                'uuid': str(self.transaction.fulfillment_identifier),
            }
        ]

        # Call to enterprise catalog, fetching course metadata
        mock_fetch_course_metadata_client.get_content_metadata.return_value = {
            'key': self.course_key,
            'content_type': 'course',
            'uuid': self.course_uuid,
            'title': 'Demonstration Course',
            'course_runs': [{
                'key': self.transaction.content_key,
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
                'course_uuid': self.course_uuid,
            }],
            'entitlements': self.course_entitlements,
            'modified': '2022-05-26T15:46:24.355321Z',
            'additional_metadata': None,
            'enrollment_count': 0,
            'recent_enrollment_count': 0,
            'course_run_keys': [self.courserun_key],
            'content_last_modified': '2023-03-06T20:56:46Z',
            'enrollment_url': 'https://foobar.com',
            'active': False
        }

        assert Reversal.objects.count() == 0

        call_command('write_reversals_from_enterprise_unenrollments', dry_run=dry_run_enabled)

        if not dry_run_enabled:
            assert Reversal.objects.count() == 1
            reversal = Reversal.objects.first()
            assert reversal.transaction == self.transaction
            assert reversal.idempotency_key == \
                f'unenrollment-reversal-{self.transaction.fulfillment_identifier}-2023-06-1T19:27:29Z'
        else:
            assert Reversal.objects.count() == 0
