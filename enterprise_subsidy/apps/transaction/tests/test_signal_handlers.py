"""
Tests for the subsidy service transaction app signal handlers
"""
from unittest import mock

import pytest
from django.test import TestCase
from openedx_events.enterprise.signals import SUBSIDY_REDEMPTION_REVERSED
from openedx_ledger.signals.signals import TRANSACTION_REVERSED
from openedx_ledger.test_utils.factories import LedgerFactory, ReversalFactory, TransactionFactory

from enterprise_subsidy.apps.api_client.enterprise import EnterpriseApiClient
from test_utils.utils import MockResponse


class TransactionSignalHandlerTestCase(TestCase):
    """
    Tests for the transaction signal handlers
    """
    def setUp(self):
        super().setUp()
        self.receiver_called = False

    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_transaction_reversed_signal_handler_catches_event(self, mock_oauth_client):
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

    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_transaction_reversed_signal_without_fulfillment_identifier(self, mock_oauth_client):
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

    def _event_receiver_side_effect(self, **kwargs):
        """
        Used show that the Open edX Event was called by the Django signal handler.
        """
        self.receiver_called = True

    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_transaction_reversed_signal_handler_produces_redemption_reversal_event(self, mock_oauth_client):
        """
        Test that the transaction reversed signal handler produces the redemption reversal event on the bus
        """
        mock_oauth_client.return_value.post.return_value = MockResponse({}, 201)
        ledger = LedgerFactory()
        transaction = TransactionFactory(
            ledger=ledger,
            quantity=100,
            fulfillment_identifier='foobar',
            subsidy_access_policy_uuid='d13d16c8-d299-40f8-9bb1-19bf12b2af72'
        )
        reversal = ReversalFactory(transaction=transaction)
        event_receiver = mock.Mock(side_effect=self._event_receiver_side_effect)
        SUBSIDY_REDEMPTION_REVERSED.connect(event_receiver)
        TRANSACTION_REVERSED.send(sender=self, reversal=reversal)
        self.assertTrue(self.receiver_called)
        self.assertEqual(
            event_receiver.call_args.kwargs['redemption'].subsidy_identifier,
            transaction.subsidy_access_policy_uuid
        )
        self.assertEqual(
            event_receiver.call_args.kwargs['redemption'].content_key,
            transaction.content_key
        )
        self.assertEqual(
            event_receiver.call_args.kwargs['redemption'].lms_user_id,
            transaction.lms_user_id
        )
