"""
Tests for functionality provided in the ``models.py`` module.
"""
from itertools import product
from unittest import mock
from uuid import uuid4

import ddt
import pytest
from django.test import TestCase
from openedx_ledger.models import Transaction, TransactionStateChoices
from openedx_ledger.test_utils.factories import (
    ExternalFulfillmentProviderFactory,
    ExternalTransactionReferenceFactory,
    TransactionFactory
)
from requests.exceptions import HTTPError
from rest_framework import status

from enterprise_subsidy.apps.fulfillment.api import InvalidFulfillmentMetadataException
from test_utils.utils import MockResponse

from ..models import ContentNotFoundForCustomerException, Subsidy
from .factories import SubsidyFactory


@ddt.ddt
class SubsidyModelReadTestCase(TestCase):
    """
    Tests functionality defined in the ``Subsidy`` model.
    """
    @classmethod
    def setUpTestData(cls):
        """
        We assume that tests in this class don't mutate self.subsidy,
        or if they do, take care to reset/clean-up the subsidy state
        at the end of the test.  This allows us to use setUpTestData(),
        which runs only once before every test in this TestCase is run.
        """
        cls.enterprise_customer_uuid = uuid4()
        cls.subsidy = SubsidyFactory.create(
            enterprise_customer_uuid=cls.enterprise_customer_uuid,
        )
        cls.subsidy.content_metadata_api = mock.MagicMock()
        super().setUpTestData()

    def test_price_for_content(self):
        """
        Tests that Subsidy.price_for_content returns the price of a piece
        of content from the catalog client converted to cents of a dollar.
        """
        content_price_cents = 19998

        self.subsidy.content_metadata_api().get_course_price.return_value = content_price_cents

        actual_price_cents = self.subsidy.price_for_content('some-content-key')
        self.assertEqual(actual_price_cents, content_price_cents)
        self.subsidy.content_metadata_api().get_course_price.assert_called_once_with(
            self.enterprise_customer_uuid,
            'some-content-key',
        )

    def test_is_redeemable_no_price(self):
        """
        When no price is available, a course is NOT redeemable
        """
        content_price_cents = None
        self.subsidy.content_metadata_api().get_course_price.return_value = content_price_cents
        redeemable, _ = self.subsidy.is_redeemable('some-content-key')
        assert not redeemable

    def test_is_redeemable_with_price(self):
        """
        Given a valid price, a course IS redeemable
        """
        content_price_cents = 1000
        self.subsidy.content_metadata_api().get_course_price.return_value = content_price_cents
        redeemable, _ = self.subsidy.is_redeemable('some-content-key')
        assert redeemable

    def test_is_redeemable_with_zero_price(self):
        """
        Given a valid price, a course IS redeemable, zero is a valid price
        """
        content_price_cents = 0
        self.subsidy.content_metadata_api().get_course_price.return_value = content_price_cents
        redeemable, _ = self.subsidy.is_redeemable('some-content-key')
        assert redeemable

    def test_price_for_content_not_in_catalog(self):
        """
        Tests that Subsidy.price_for_content raises ContentNotFoundForCustomerException
        if the content is not part of any catalog for the customer.
        """
        self.subsidy.content_metadata_api().get_course_price.side_effect = HTTPError(
            response=MockResponse(None, status.HTTP_404_NOT_FOUND),
        )

        with self.assertRaises(ContentNotFoundForCustomerException):
            self.subsidy.price_for_content('some-content-key')

    @ddt.data(True, False)
    def test_is_redeemable(self, expected_to_be_redeemable):
        """
        Tests that Subsidy.is_redeemable() returns true when the subsidy
        has enough remaining balance to cover the price of the given content,
        and false otherwise.
        """
        # Mock the content price to be slightly too expensive if
        # expected_to_be_redeemable is false;
        # mock it to be slightly affordable if true.
        constant = -100 if expected_to_be_redeemable else 100
        content_price = self.subsidy.current_balance() + constant
        self.subsidy.content_metadata_api().get_course_price.return_value = content_price

        is_redeemable, actual_content_price = self.subsidy.is_redeemable('some-content-key')

        self.assertEqual(is_redeemable, expected_to_be_redeemable)
        self.assertEqual(content_price, actual_content_price)


class SubsidyModelRedemptionTestCase(TestCase):
    """
    Tests functionality related to redemption on the Subsidy model
    """
    def setUp(self):
        self.enterprise_customer_uuid = uuid4()
        self.subsidy_access_policy_uuid = uuid4()
        self.subsidy = SubsidyFactory.create(
            enterprise_customer_uuid=self.enterprise_customer_uuid,
        )
        super().setUp()

    def test_get_committed_transaction_no_reversal(self):
        """
        Tests that get_redemption appropriately filters by learner and content identifiers.
        """
        alice_lms_user_id, bob_lms_user_id = (23, 42)
        learner_content_pairs = list(product(
            (alice_lms_user_id, bob_lms_user_id),
            ('science-content-key', 'art-content-key'),
        ))
        for lms_user_id, content_key in learner_content_pairs:
            TransactionFactory.create(
                state=TransactionStateChoices.COMMITTED,
                quantity=-1000,
                ledger=self.subsidy.ledger,
                lms_user_id=lms_user_id,
                content_key=content_key
            )

        for lms_user_id, content_key in learner_content_pairs:
            transaction = self.subsidy.get_committed_transaction_no_reversal(lms_user_id, content_key)
            self.assertEqual(transaction.lms_user_id, lms_user_id)
            self.assertEqual(transaction.content_key, content_key)
            self.assertEqual(transaction.quantity, -1000)
            self.assertEqual(transaction.state, TransactionStateChoices.COMMITTED)

    def test_commit_transaction(self):
        """
        Tests that commit_transaction creates a transaction with the correct state.
        """
        transaction = TransactionFactory.create(
            state=TransactionStateChoices.PENDING,
            ledger=self.subsidy.ledger,
        )
        fulfillment_identifier = 'some-fulfillment-identifier'
        provider = ExternalFulfillmentProviderFactory()
        external_reference = ExternalTransactionReferenceFactory(
            external_fulfillment_provider=provider,
        )
        self.subsidy.commit_transaction(
            ledger_transaction=transaction,
            fulfillment_identifier=fulfillment_identifier,
            external_reference=external_reference,
        )
        transaction.refresh_from_db()
        self.assertEqual(
            transaction.external_reference.first(),
            external_reference
        )
        self.assertEqual(
            transaction.external_reference.first().external_fulfillment_provider,
            provider
        )

    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content')
    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.enterprise_client')
    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_summary")
    def test_redeem_not_existing(self, mock_get_content_summary, mock_enterprise_client, mock_price_for_content):
        """
        Test Subsidy.redeem() happy path (i.e. the redemption/transaction does not already exist, and calling redeem()
        creates one).
        """
        lms_user_id = 1
        content_key = "course-v1:edX+test+course"
        subsidy_access_policy_uuid = str(uuid4())
        mock_enterprise_fulfillment_uuid = str(uuid4())
        mock_content_price = 1000
        mock_get_content_summary.return_value = {
            'content_uuid': 'course-v1:edX+test+course',
            'content_key': 'course-v1:edX+test+course',
            'source': 'edX',
            'mode': 'verified',
            'content_price': 10000,
            'geag_variant_id': None,
        }
        mock_price_for_content.return_value = mock_content_price
        mock_enterprise_client.enroll.return_value = mock_enterprise_fulfillment_uuid
        new_transaction, transaction_created = self.subsidy.redeem(
            lms_user_id,
            content_key,
            subsidy_access_policy_uuid
        )
        assert transaction_created
        assert new_transaction.state == TransactionStateChoices.COMMITTED
        assert new_transaction.quantity == -mock_content_price

    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content')
    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.enterprise_client')
    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_summary")
    def test_redeem_with_metadata(self, mock_get_content_summary, mock_enterprise_client, mock_price_for_content):
        """
        Test Subsidy.redeem() happy path with additional metadata
        """
        lms_user_id = 1
        content_key = "course-v1:edX+test+course"
        subsidy_access_policy_uuid = str(uuid4())
        mock_enterprise_fulfillment_uuid = str(uuid4())
        mock_content_price = 1000
        mock_get_content_summary.return_value = {
            'content_uuid': 'course-v1:edX+test+course',
            'content_key': 'course-v1:edX+test+course',
            'source': 'edX',
            'mode': 'verified',
            'content_price': 10000,
            'geag_variant_id': None,
        }
        mock_price_for_content.return_value = mock_content_price
        mock_enterprise_client.enroll.return_value = mock_enterprise_fulfillment_uuid
        tx_metadata = {
            'geag_first_name': 'Donny',
            'geag_last_name': 'Kerabatsos',
        }
        new_transaction, transaction_created = self.subsidy.redeem(
            lms_user_id,
            content_key,
            subsidy_access_policy_uuid,
            metadata=tx_metadata
        )
        assert transaction_created
        assert new_transaction.state == TransactionStateChoices.COMMITTED
        assert new_transaction.quantity == -mock_content_price
        assert new_transaction.metadata == tx_metadata

    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content')
    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.enterprise_client')
    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_summary")
    def test_redeem_with_geag_exception(self, mock_get_content_summary, mock_enterprise_client, mock_price_for_content):
        """
        Test Subsidy.redeem() rollback upon geag validation exception
        """
        lms_user_id = 1
        content_key = "course-v1:edX+test+course"
        subsidy_access_policy_uuid = str(uuid4())
        mock_enterprise_fulfillment_uuid = str(uuid4())
        mock_content_price = 1000
        mock_get_content_summary.return_value = {
            'content_uuid': 'course-v1:edX+test+course',
            'content_key': 'course-v1:edX+test+course',
            'source': 'edX',
            'mode': 'verified',
            'content_price': 10000,
            'geag_variant_id': str(uuid4()),
        }
        mock_price_for_content.return_value = mock_content_price
        mock_enterprise_client.enroll.return_value = mock_enterprise_fulfillment_uuid
        tx_metadata = {
            'geag_first_name': 'Donny',
            'geag_last_name': 'Kerabatsos',
        }
        with pytest.raises(InvalidFulfillmentMetadataException):
            self.subsidy.redeem(
                lms_user_id,
                content_key,
                subsidy_access_policy_uuid,
                metadata=tx_metadata
            )
        created_transaction = Transaction.objects.latest('created')
        assert created_transaction.state == TransactionStateChoices.FAILED


class SubsidyManagerTestCase(TestCase):
    """
    Tests for the custom managers on the Subsidy model
    """
    def setUp(self):
        Subsidy.objects.all().delete()

    def test_active_subsidy_manager(self):
        """
        Test that the ActiveSubsidyManager only retrieves non-soft-deleted subsidies
        """
        SubsidyFactory.create(is_soft_deleted=True)
        SubsidyFactory.create(is_soft_deleted=False)
        self.assertEqual(Subsidy.objects.count(), 1)
        self.assertEqual(Subsidy.all_objects.count(), 2)
