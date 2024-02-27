"""
Test the Enterprise Subsidy service management commands and related functions.
"""

import uuid
from unittest import mock

import ddt
from django.core.management import call_command
from django.test import TestCase, override_settings
from openedx_ledger.models import Reversal, TransactionStateChoices
from openedx_ledger.test_utils.factories import (
    ExternalFulfillmentProviderFactory,
    ExternalTransactionReferenceFactory,
    LedgerFactory,
    ReversalFactory,
    TransactionFactory
)
from pytest import mark

from enterprise_subsidy.apps.fulfillment.api import GEAGFulfillmentHandler
from enterprise_subsidy.apps.fulfillment.exceptions import FulfillmentException
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
        self.geag_fulfillment_identifier = str(uuid.uuid4())
        self.unknown_fulfillment_identifier = str(uuid.uuid4())
        self.transaction = TransactionFactory(
            ledger=self.ledger,
            quantity=100,
            fulfillment_identifier=self.fulfillment_identifier
        )
        self.geag_transaction = TransactionFactory(
            ledger=self.ledger,
            fulfillment_identifier=self.geag_fulfillment_identifier,
        )
        self.geag_provider = ExternalFulfillmentProviderFactory(
            slug=GEAGFulfillmentHandler.EXTERNAL_FULFILLMENT_PROVIDER_SLUG,
        )
        self.geag_reference = ExternalTransactionReferenceFactory(
            external_fulfillment_provider=self.geag_provider,
            transaction=self.geag_transaction,
        )
        self.geag_second_reference = ExternalTransactionReferenceFactory(
            external_fulfillment_provider=self.geag_provider,
            transaction=self.geag_transaction,
        )
        self.unknown_transaction = TransactionFactory(
            ledger=self.ledger,
            fulfillment_identifier=self.unknown_fulfillment_identifier,
        )
        self.unknown_provider = ExternalFulfillmentProviderFactory(slug='unknown')
        self.unknown_reference = ExternalTransactionReferenceFactory(
            external_fulfillment_provider=self.unknown_provider,
            transaction=self.unknown_transaction,
        )

        self.transaction_to_backpopulate = TransactionFactory(
            ledger=self.ledger,
            lms_user_email=None,
            content_title=None,
            # We can't just set parent_content_key to None because it will break content_key (derived factory field).
            # Do it after object creation.
            # parent_content_key=None,
            quantity=100,
            fulfillment_identifier=self.fulfillment_identifier
        )
        self.transaction_to_backpopulate.parent_content_key = None
        self.transaction_to_backpopulate.save()

        self.internal_ledger = LedgerFactory()
        self.internal_subsidy = SubsidyFactory(ledger=self.internal_ledger, internal_only=True)
        self.internal_transaction_to_backpopulate = TransactionFactory(
            ledger=self.internal_ledger,
            lms_user_email=None,
            content_title=None,
        )
        self.internal_transaction_to_backpopulate.parent_content_key = None
        self.internal_transaction_to_backpopulate.save()

        self.transaction_not_to_backpopulate = TransactionFactory(
            ledger=self.ledger,

            # Setting content_key or lms_user_id to None force-disables backpopulation.
            content_key=None,
            lms_user_id=None,

            # The target fields to backpopulate are empty, nevertheless.
            lms_user_email=None,
            content_title=None,
            parent_content_key=None,
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

    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_write_reversals_from_enterprise_unenrollment_with_uncommitted_transaction(self, mock_oauth_client):
        """
        Test that the write_reversals_from_enterprise_unenrollments management command does not create a reversal if
        the transaction is not committed.
        """
        mock_oauth_client.return_value.get.return_value = MockResponse(
            [{
                'enterprise_course_enrollment': {
                    'enterprise_customer_user': 10,
                    'course_id': self.courserun_key,
                    'created': '2023-05-25T19:27:29Z',
                    'unenrolled_at': '2023-06-1T19:27:29Z',
                },
                'transaction_id': self.transaction.uuid,
                'uuid': self.fulfillment_identifier,
            }],
            200
        )
        self.transaction.state = TransactionStateChoices.CREATED
        self.transaction.save()
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
    @override_settings(ENTERPRISE_SUBSIDY_AUTOMATIC_EXTERNAL_CANCELLATION=False)
    def test_write_reversals_from_geag_enterprise_unenrollments_disabled_setting(
        self,
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
                    'course_id': self.geag_transaction.content_key,
                    'created': '2023-05-25T19:27:29Z',
                    'unenrolled_at': '2023-06-1T19:27:29Z',
                },
                'transaction_id': self.geag_transaction.uuid,
                'uuid': str(self.geag_transaction.fulfillment_identifier),
            }
        ]

        # Call to enterprise catalog, fetching course metadata
        mock_fetch_course_metadata_client.get_content_metadata.return_value = {
            'key': self.course_key,
            'content_type': 'course',
            'uuid': self.course_uuid,
            'title': 'Demonstration Course',
            'course_runs': [{
                'key': self.geag_transaction.content_key,
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

        call_command('write_reversals_from_enterprise_unenrollments')

        assert Reversal.objects.count() == 0

    @mock.patch(
        'enterprise_subsidy.apps.transaction.management.commands.write_reversals_from_enterprise_unenrollments.'
        'GetSmarterEnterpriseApiClient'
    )
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
    @override_settings(ENTERPRISE_SUBSIDY_AUTOMATIC_EXTERNAL_CANCELLATION=True)
    def test_write_reversals_from_geag_enterprise_unenrollments_enabled_setting(
        self,
        mock_signal_client,
        mock_fetch_course_metadata_client,
        mock_fetch_recent_unenrollments_client,
        mock_geag_client,
    ):
        """
        Test the write_reversals_from_enterprise_unenrollments management command's ability to create a reversal.
        """
        # Reversal creation will trigger a signal handler that will make a call to enterprise
        mock_signal_client.return_value = mock.MagicMock()

        mock_geag_client.return_value = mock.MagicMock()
        # mock_geag_client.return_value.cancel_enterprise_allocation.return_value = True

        # Call to enterprise, fetching recent unenrollments
        mock_fetch_recent_unenrollments_client.return_value.fetch_recent_unenrollments.return_value = [
            {
                'enterprise_course_enrollment': {
                    'enterprise_customer_user': 10,
                    'course_id': self.geag_transaction.content_key,
                    'created': '2023-05-25T19:27:29Z',
                    'unenrolled_at': '2023-06-1T19:27:29Z',
                },
                'transaction_id': self.geag_transaction.uuid,
                'uuid': str(self.geag_transaction.fulfillment_identifier),
            }
        ]

        # Call to enterprise catalog, fetching course metadata
        mock_fetch_course_metadata_client.get_content_metadata.return_value = {
            'key': self.course_key,
            'content_type': 'course',
            'uuid': self.course_uuid,
            'title': 'Demonstration Course',
            'course_runs': [{
                'key': self.geag_transaction.content_key,
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
    @override_settings(ENTERPRISE_SUBSIDY_AUTOMATIC_EXTERNAL_CANCELLATION=True)
    def test_write_reversals_from_geag_enterprise_unenrollments_unknown_provider(
        self,
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
                    'course_id': self.unknown_transaction.content_key,
                    'created': '2023-05-25T19:27:29Z',
                    'unenrolled_at': '2023-06-1T19:27:29Z',
                },
                'transaction_id': self.unknown_transaction.uuid,
                'uuid': str(self.unknown_transaction.fulfillment_identifier),
            }
        ]

        # Call to enterprise catalog, fetching course metadata
        mock_fetch_course_metadata_client.get_content_metadata.return_value = {
            'key': self.course_key,
            'content_type': 'course',
            'uuid': self.course_uuid,
            'title': 'Demonstration Course',
            'course_runs': [{
                'key': self.unknown_transaction.content_key,
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
        with self.assertRaises(FulfillmentException):
            call_command('write_reversals_from_enterprise_unenrollments')
        assert Reversal.objects.count() == 0

    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.lms_user_client")
    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_summary")
    def test_backpopulate_transaction_email_and_title(
        self,
        mock_get_content_summary,
        mock_lms_user_client,
    ):
        """
        Test that the backpopulate_transaction_email_and_title management command backpopulates the email and title
        """
        expected_email_address = 'edx@example.com'
        mock_lms_user_client.return_value.best_effort_user_data.return_value = {
            'email': expected_email_address,
        }
        expected_content_title = 'a content title'
        mock_get_content_summary.return_value = {
            'content_uuid': 'a content uuid',
            'content_key': 'a content key',
            'content_title': expected_content_title,
            'source': 'edX',
            'mode': 'verified',
            'content_price': 10000,
            'geag_variant_id': None,
        }
        call_command('backpopulate_transaction_email_and_title')
        self.transaction_to_backpopulate.refresh_from_db()
        self.internal_transaction_to_backpopulate.refresh_from_db()
        self.transaction_not_to_backpopulate.refresh_from_db()
        assert self.transaction_to_backpopulate.lms_user_email == expected_email_address
        assert self.transaction_to_backpopulate.content_title == expected_content_title
        assert self.internal_transaction_to_backpopulate.lms_user_email is None
        assert self.internal_transaction_to_backpopulate.content_title is None
        assert self.transaction_not_to_backpopulate.lms_user_email is None
        assert self.transaction_not_to_backpopulate.content_title is None

    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.lms_user_client")
    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_summary")
    def test_backpopulate_transaction_email_and_title_include_internal(
        self,
        mock_get_content_summary,
        mock_lms_user_client,
    ):
        """
        Test that the backpopulate_transaction_email_and_title while including internal subsidies
        """
        expected_email_address = 'edx@example.com'
        mock_lms_user_client.return_value.best_effort_user_data.return_value = {
            'email': expected_email_address,
        }
        expected_content_title = 'a content title'
        mock_get_content_summary.return_value = {
            'content_uuid': 'a content uuid',
            'content_key': 'a content key',
            'content_title': expected_content_title,
            'source': 'edX',
            'mode': 'verified',
            'content_price': 10000,
            'geag_variant_id': None,
        }
        call_command('backpopulate_transaction_email_and_title', include_internal_subsidies=True)
        self.transaction_to_backpopulate.refresh_from_db()
        self.internal_transaction_to_backpopulate.refresh_from_db()
        self.transaction_not_to_backpopulate.refresh_from_db()
        assert self.transaction_to_backpopulate.lms_user_email == expected_email_address
        assert self.transaction_to_backpopulate.content_title == expected_content_title
        assert self.internal_transaction_to_backpopulate.lms_user_email == expected_email_address
        assert self.internal_transaction_to_backpopulate.content_title == expected_content_title
        assert self.transaction_not_to_backpopulate.lms_user_email is None
        assert self.transaction_not_to_backpopulate.content_title is None

    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_metadata")
    def test_backpopulate_transaction_parent_content_key(
        self,
        mock_get_content_metadata,
    ):
        """
        Test that the backpopulate_transaction_parent_content_key management command backpopulates the
        parent_content_key.
        """
        expected_parent_content_key = 'edx+101'
        mock_get_content_metadata.return_value = {
            'aggregation_key': f'courserun:{expected_parent_content_key}',
            # Remainder of raw content metdata not needed to be mocked.
        }
        call_command('backpopulate_transaction_parent_content_key')
        self.transaction_to_backpopulate.refresh_from_db()
        self.internal_transaction_to_backpopulate.refresh_from_db()
        self.transaction_not_to_backpopulate.refresh_from_db()
        assert self.transaction_to_backpopulate.parent_content_key == expected_parent_content_key
        assert self.internal_transaction_to_backpopulate.parent_content_key is None
        assert self.transaction_not_to_backpopulate.parent_content_key is None

    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_metadata")
    def test_backpopulate_transaction_parent_content_key_include_internal(
        self,
        mock_get_content_metadata,
    ):
        """
        Test backpopulate_transaction_parent_content_key while including internal subsidies.
        """
        expected_parent_content_key = 'edx+101'
        mock_get_content_metadata.return_value = {
            'aggregation_key': f'courserun:{expected_parent_content_key}',
            # Remainder of raw content metdata not needed to be mocked.
        }
        call_command('backpopulate_transaction_parent_content_key', include_internal_subsidies=True)
        self.transaction_to_backpopulate.refresh_from_db()
        self.internal_transaction_to_backpopulate.refresh_from_db()
        self.transaction_not_to_backpopulate.refresh_from_db()
        assert self.transaction_to_backpopulate.parent_content_key == expected_parent_content_key
        assert self.internal_transaction_to_backpopulate.parent_content_key == expected_parent_content_key
        assert self.transaction_not_to_backpopulate.parent_content_key is None
