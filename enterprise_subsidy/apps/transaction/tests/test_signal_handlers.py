"""
Tests for the subsidy service transaction app signal handlers
"""
import re
from datetime import datetime
from unittest import mock
from uuid import uuid4

import ddt
import pytest
from django.test import TestCase
from django.test.utils import override_settings
from openedx_ledger.models import TransactionStateChoices
from openedx_ledger.signals.signals import TRANSACTION_REVERSED
from openedx_ledger.test_utils.factories import (
    ExternalFulfillmentProviderFactory,
    ExternalTransactionReferenceFactory,
    LedgerFactory,
    ReversalFactory,
    TransactionFactory
)

from enterprise_subsidy.apps.api_client.enterprise import EnterpriseApiClient
from enterprise_subsidy.apps.fulfillment.api import GEAGFulfillmentHandler
from enterprise_subsidy.apps.transaction.signals.handlers import handle_lc_enrollment_revoked
from test_utils.utils import MockResponse


@ddt.ddt
class TransactionSignalHandlerTestCase(TestCase):
    """
    Tests for the transaction signal handlers
    """

    @mock.patch('enterprise_subsidy.apps.transaction.signals.handlers.send_transaction_reversed_event')
    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_transaction_reversed_signal_handler_catches_event(self, mock_oauth_client, mock_send_event_bus_reversed):
        """
        Test that the transaction reversed signal handler catches the transaction reversed event when it's emitted
        """
        mock_oauth_client.return_value.post.return_value = MockResponse({}, 201)
        ledger = LedgerFactory()
        transaction = TransactionFactory(ledger=ledger, quantity=100, fulfillment_identifier='foobar')
        reversal = ReversalFactory(transaction=transaction)
        TRANSACTION_REVERSED.send(sender=self, reversal=reversal)
        assert mock_oauth_client.return_value.post.call_args.args == (
            EnterpriseApiClient.enterprise_subsidy_fulfillment_endpoint +
            f"{transaction.fulfillment_identifier}/cancel-fulfillment",
        )
        mock_send_event_bus_reversed.assert_called_once_with(transaction)

    @mock.patch('enterprise_subsidy.apps.transaction.signals.handlers.send_transaction_reversed_event')
    @mock.patch('enterprise_subsidy.apps.fulfillment.api.GetSmarterEnterpriseApiClient')
    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_reversed_signal_causes_internal_and_external_unfulfillment(
        self, mock_oauth_client, mock_geag_client, mock_send_event_bus_reversed
    ):
        """
        Tests that the signal handler cancels internal and external fulfillments
        related to the reversed transaction.
        """
        mock_oauth_client.return_value.post.return_value = MockResponse({}, 201)
        ledger = LedgerFactory()
        transaction = TransactionFactory(ledger=ledger, quantity=100, fulfillment_identifier='foobar')
        geag_provider = ExternalFulfillmentProviderFactory(
            slug=GEAGFulfillmentHandler.EXTERNAL_FULFILLMENT_PROVIDER_SLUG,
        )
        geag_reference = ExternalTransactionReferenceFactory(
            external_fulfillment_provider=geag_provider,
            transaction=transaction,
        )

        reversal = ReversalFactory(transaction=transaction)
        TRANSACTION_REVERSED.send(sender=self, reversal=reversal)

        assert mock_oauth_client.return_value.post.call_args.args == (
            EnterpriseApiClient.enterprise_subsidy_fulfillment_endpoint +
            f"{transaction.fulfillment_identifier}/cancel-fulfillment",
        )
        mock_geag_client().cancel_enterprise_allocation.assert_called_once_with(
            geag_reference.external_reference_id,
        )
        mock_send_event_bus_reversed.assert_called_once_with(transaction)

    @mock.patch('enterprise_subsidy.apps.transaction.signals.handlers.send_transaction_reversed_event')
    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_transaction_reversed_signal_without_fulfillment_identifier(
        self, mock_oauth_client, mock_send_event_bus_reversed
    ):
        """
        Test that the transaction reversed signal handler does not call the api client if the transaction has no
        fulfillment identifier
        """
        # mock_oauth_client.return_value.post.return_value = MockResponse({}, 201)
        ledger = LedgerFactory()
        transaction = TransactionFactory(ledger=ledger, quantity=100, fulfillment_identifier=None)
        reversal = ReversalFactory(transaction=transaction)
        with pytest.raises(ValueError):
            TRANSACTION_REVERSED.send(sender=self, reversal=reversal)

        assert mock_oauth_client.return_value.post.call_count == 0
        self.assertFalse(mock_send_event_bus_reversed.called)

    @ddt.data(
        # Happy path.
        {},
        # Sad paths:
        {
            "transaction_state": None,
            "expected_log_regex": "No Subsidy Transaction found",
            "expected_reverse_transaction_called": False,
        },
        {
            "transaction_state": TransactionStateChoices.PENDING,
            "expected_log_regex": "not in a committed state",
            "expected_reverse_transaction_called": False,
        },
        {
            "reversal_exists": True,
            "expected_log_regex": "Found existing Reversal",
            "expected_reverse_transaction_called": False,
        },
        {
            "refundable": False,
            "expected_log_regex": "not refundable",
            "expected_reverse_transaction_called": False,
        },
        {
            "external_fulfillment_will_succeed": False,
            "expected_log_regex": "no reversal written",
            "expected_reverse_transaction_called": False,
        },
    )
    @ddt.unpack
    @mock.patch('enterprise_subsidy.apps.transaction.signals.handlers.cancel_transaction_external_fulfillment')
    @mock.patch('enterprise_subsidy.apps.transaction.signals.handlers.reverse_transaction')
    @mock.patch('enterprise_subsidy.apps.transaction.signals.handlers.unenrollment_can_be_refunded')
    @mock.patch('enterprise_subsidy.apps.transaction.signals.handlers.ContentMetadataApi.get_content_metadata')
    @override_settings(ENABLE_HANDLE_LC_ENROLLMENT_REVOKED=True)
    def test_handle_lc_enrollment_revoked(
        self,
        mock_get_content_metadata,
        mock_unenrollment_can_be_refunded,
        mock_reverse_transaction,
        mock_cancel_transaction_external_fulfillment,
        transaction_state=TransactionStateChoices.COMMITTED,
        reversal_exists=False,
        refundable=True,
        external_fulfillment_will_succeed=True,
        expected_log_regex=None,
        expected_reverse_transaction_called=True,
    ):
        mock_get_content_metadata.return_value = {"unused": "unused"}
        mock_unenrollment_can_be_refunded.return_value = refundable
        mock_cancel_transaction_external_fulfillment.return_value = external_fulfillment_will_succeed
        ledger = LedgerFactory()
        transaction = None
        if transaction_state:
            transaction = TransactionFactory(ledger=ledger, state=transaction_state)
        if reversal_exists:
            ReversalFactory(
                transaction=transaction,
                quantity=-transaction.quantity,
            )
        enrollment_unenrolled_at = datetime(2020, 1, 1)
        test_lc_course_enrollment = {
            "uuid": uuid4(),
            "transaction_id": transaction.uuid if transaction else uuid4(),
            "enterprise_course_enrollment": {
                "course_id": "course-v1:bin+bar+baz",
                "unenrolled_at": enrollment_unenrolled_at,
                "enterprise_customer_user": {
                    "unused": "unused",
                },
            }
        }
        with self.assertLogs(level='INFO') as logs:
            handle_lc_enrollment_revoked(learner_credit_course_enrollment=test_lc_course_enrollment)
        if expected_log_regex:
            assert any(re.search(expected_log_regex, log) for log in logs.output)
        if expected_reverse_transaction_called:
            mock_reverse_transaction.assert_called_once_with(transaction, unenroll_time=enrollment_unenrolled_at)
