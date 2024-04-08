"""
Tests for the subsidy service transaction app views
"""
from unittest import mock
from uuid import uuid4

import pytest
from django.test import TestCase
from django.urls import reverse
from openedx_ledger.test_utils.factories import (
    ExternalFulfillmentProviderFactory,
    ExternalTransactionReferenceFactory,
    LedgerFactory,
    TransactionFactory
)
from rest_framework.test import APITestCase

from enterprise_subsidy.apps.api_client.enterprise import EnterpriseApiClient
from enterprise_subsidy.apps.core.models import User
from enterprise_subsidy.apps.fulfillment.api import GEAGFulfillmentHandler
from test_utils.utils import MockResponse


@pytest.mark.django_db
class ViewTestBases(APITestCase, TestCase):
    """
    Base class for view tests, includes helper methods for creating test data and formatting urls
    """

    def setUp(self):
        super().setUp()
        self.client.force_login(User.objects.get_or_create(username='testuser', is_superuser=True, is_staff=True)[0])

        self.ledger = LedgerFactory()
        self.fulfillment_identifier = 'foobar'
        self.transaction = TransactionFactory(
            ledger=self.ledger,
            quantity=100,
            fulfillment_identifier=self.fulfillment_identifier
        )

    def get_unenroll_from_transaction_url(self, transaction_id):
        """
        helper method to get the url for the reverse transaction view
        """
        return reverse('admin:unenroll', args=(transaction_id,))


@pytest.mark.django_db
class UnenrollTransactionViewTests(ViewTestBases):
    """
    Tests for the reverse transaction view
    """

    def test_unenroll_view_get(self):
        """
        Test expected behaviors of the reverse transaction view get request
        """
        url = self.get_unenroll_from_transaction_url(self.transaction.uuid)
        response = self.client.get(url)
        assert bytes(
            'This action will unenroll the learner WITHOUT issuing a credit refund to the learner',
            'utf-8'
        ) in response.content

    def test_unenroll_view_get_with_nonexisting_transaction(self):
        """
        Test expected behaviors of the reverse transaction view get request
        """
        url = self.get_unenroll_from_transaction_url(uuid4())
        response = self.client.get(url)
        assert response.status_code == 400
        assert bytes('Transaction not found', 'utf-8') in response.content

    def test_unenroll_view_get_with_transaction_without_fulfillment_identifier(self):
        """
        Test expected behaviors of the reverse transaction view get request
        """
        self.transaction.fulfillment_identifier = None
        self.transaction.save()
        url = self.get_unenroll_from_transaction_url(self.transaction.uuid)
        response = self.client.get(url)
        assert response.status_code == 400
        assert bytes('Transaction has no associated platform fulfillment identifier', 'utf-8') in response.content

    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_unenroll_view_post(self, mock_oauth_client):
        """
        Test expected behaviors of the unenroll view post request
        """
        mock_oauth_client.return_value.post.return_value = MockResponse(
            {'data': 'success'},
            201,
        )

        url = self.get_unenroll_from_transaction_url(self.transaction.uuid)
        response = self.client.post(url)
        assert response.status_code == 302
        assert mock_oauth_client.return_value.post.call_count == 1
        assert mock_oauth_client.return_value.post.call_args.args == (
            EnterpriseApiClient.enterprise_subsidy_fulfillment_endpoint +
            f"{self.transaction.fulfillment_identifier}/cancel-fulfillment",
        )

    @mock.patch('enterprise_subsidy.apps.fulfillment.api.GetSmarterEnterpriseApiClient')
    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_unenroll_view_post_with_external_transaction(self, mock_oauth_client, mock_geag_client):
        """
        Test expected behaviors of the unenroll view post request
        """
        fulfillment_identifier = uuid4()
        transaction = TransactionFactory(
            ledger=self.ledger,
            fulfillment_identifier=fulfillment_identifier,
        )
        geag_provider = ExternalFulfillmentProviderFactory(
            slug=GEAGFulfillmentHandler.EXTERNAL_FULFILLMENT_PROVIDER_SLUG,
        )
        geag_reference = ExternalTransactionReferenceFactory(
            external_fulfillment_provider=geag_provider,
            transaction=transaction,
        )
        mock_oauth_client.return_value.post.return_value = MockResponse(
            {'data': 'success'},
            201,
        )

        url = self.get_unenroll_from_transaction_url(transaction.uuid)
        response = self.client.post(url)
        assert response.status_code == 302
        assert mock_oauth_client.return_value.post.call_count == 1
        assert mock_oauth_client.return_value.post.call_args.args == (
            EnterpriseApiClient.enterprise_subsidy_fulfillment_endpoint +
            f"{transaction.fulfillment_identifier}/cancel-fulfillment",
        )
        mock_geag_client().cancel_enterprise_allocation.assert_called_once_with(
            geag_reference.external_reference_id,
        )

    def test_unenroll_view_post_with_fake_transaction(self):
        """
        TTest expected behaviors of the unenroll view post request with a fake transaction
        """
        url = self.get_unenroll_from_transaction_url(uuid4())
        response = self.client.post(url)
        assert response.status_code == 400
        assert bytes('Transaction not found', 'utf-8') in response.content

    def test_unenroll_view_post_with_transaction_without_fulfillment_identifier(self):
        """
        Test expected behaviors of the unenroll view post request with a transaction without a fulfillment identifier
        """
        self.transaction.fulfillment_identifier = None
        self.transaction.save()
        url = self.get_unenroll_from_transaction_url(self.transaction.uuid)
        response = self.client.post(url)
        assert response.status_code == 400
        assert bytes('Transaction has no associated platform fulfillment identifier', 'utf-8') in response.content

    @mock.patch('enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient', return_value=mock.MagicMock())
    def test_unenroll_view_post_with_failed_call_to_platform(self, mock_oauth_client):
        """
        Test expected behaviors of the unenroll view post request when a failed call to the platform occures
        """
        mock_oauth_client.return_value.post.return_value = MockResponse(
            {'error': 'you screwed up'},
            500,
        )

        url = self.get_unenroll_from_transaction_url(self.transaction.uuid)
        response = self.client.post(url)
        assert bytes('Error canceling platform fulfillment foobar: 500 Server Error', 'utf-8') in response.content
        assert response.status_code == 400
