"""
Tests for functions defined in the ``api.py`` module.
"""
from unittest import mock
from uuid import uuid4

import pytest
from django.test import TestCase
from openedx_ledger.models import Reversal, TransactionStateChoices, UnitChoices
from openedx_ledger.test_utils.factories import TransactionFactory

from enterprise_subsidy.apps.subsidy import api as subsidy_api

from .factories import SubsidyFactory


@pytest.fixture
def learner_credit_fixture():
    """
    Simple Learner Credit Subsidy pytest fixture.
    """
    subsidy, _ = subsidy_api.get_or_create_learner_credit_subsidy(
        reference_id="test-opp-product-id",
        default_title="Test Learner Credit Subsidy",
        default_enterprise_customer_uuid=uuid4(),
        default_unit=UnitChoices.USD_CENTS,
        default_starting_balance=1000000,
    )
    return subsidy


@pytest.mark.django_db
def test_create_learner_credit_subsidy(learner_credit_fixture):  # pylint: disable=redefined-outer-name
    """
    Test that a Subsidy, associated Ledger, and initial Transaction all are
    created successfully.  This can be easily confirmed by calling
    ``subsidy.current_balance()``, which reads all 3 related objects.
    """
    assert learner_credit_fixture.current_balance() == 1000000


@pytest.mark.django_db
def test_get_learner_credit_subsidy(learner_credit_fixture):  # pylint: disable=redefined-outer-name
    """
    Test that a Subsidy can be retrieved, discarding supplied defaults.
    """
    _, created = subsidy_api.get_or_create_learner_credit_subsidy(
        reference_id=learner_credit_fixture.reference_id,
        default_title="Default Title",
        default_enterprise_customer_uuid=uuid4(),
        default_unit=UnitChoices.USD_CENTS,
        default_starting_balance=30,
    )
    assert not created
    assert learner_credit_fixture.current_balance() == 1000000


class CanRedeemTestCase(TestCase):
    """
    Test the can_redeem() function.
    """
    def setUp(self):
        self.enterprise_customer_uuid = uuid4()
        self.subsidy_access_policy_uuid = uuid4()
        self.subsidy = SubsidyFactory.create(
            enterprise_customer_uuid=self.enterprise_customer_uuid,
            starting_balance=100000,
        )
        self.subsidy.catalog_client = mock.MagicMock()
        self.subsidy.catalog_client.get_course_price.return_value = '199.98'
        self.lms_user_id = 42
        self.content_key = 'some-content-key'
        super().setUp()

    def test_no_existing_transaction(self):
        """
        Tests that when no transaction for the given learner and content exists,
        we return the result of ``Subsidy.can_redeem()``.
        """
        expected_redeemable = True
        expected_price = 19998

        actual_redeemable, actual_price, actual_transaction = subsidy_api.can_redeem(
            self.subsidy, self.lms_user_id, self.content_key
        )
        self.assertEqual(expected_redeemable, actual_redeemable)
        self.assertEqual(expected_price, actual_price)
        self.assertIsNone(actual_transaction)

    def test_existing_transaction_with_reversal(self):
        """
        Tests that when a reversed transaction for the given learner and content exists,
        we return the result of ``Subsidy.can_redeem()``.
        """
        existing_transaction = TransactionFactory.create(
            state=TransactionStateChoices.COMMITTED,
            quantity=-19998,
            ledger=self.subsidy.ledger,
            lms_user_id=self.lms_user_id,
            content_key=self.content_key
        )
        reversal = Reversal.objects.create(
            transaction=existing_transaction,
            idempotency_key=str(existing_transaction.idempotency_key) + '-reversed',
            quantity=19998,
            state=TransactionStateChoices.COMMITTED,
        )
        expected_redeemable = True
        expected_price = 19998

        actual_redeemable, actual_price, actual_transaction = subsidy_api.can_redeem(
            self.subsidy, self.lms_user_id, self.content_key
        )
        self.assertEqual(expected_redeemable, actual_redeemable)
        self.assertEqual(expected_price, actual_price)
        self.assertEqual(existing_transaction, actual_transaction)
        self.assertEqual(actual_transaction.reversal, reversal)

    def test_existing_transaction_no_reversal(self):
        """
        Tests that when a transaction with no reversal for the given learner and content exists,
        we return a result of ``False`` along with the content price and existing transaction.
        """
        existing_transaction = TransactionFactory.create(
            state=TransactionStateChoices.COMMITTED,
            quantity=-19998,
            ledger=self.subsidy.ledger,
            lms_user_id=self.lms_user_id,
            content_key=self.content_key
        )
        expected_redeemable = False
        expected_price = 19998

        actual_redeemable, actual_price, actual_transaction = subsidy_api.can_redeem(
            self.subsidy, self.lms_user_id, self.content_key
        )
        self.assertEqual(expected_redeemable, actual_redeemable)
        self.assertEqual(expected_price, actual_price)
        self.assertEqual(existing_transaction, actual_transaction)
