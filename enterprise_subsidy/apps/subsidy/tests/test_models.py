"""
Tests for functionality provided in the ``models.py`` module.
"""
import random
from itertools import product
from unittest import mock
from uuid import uuid4

import ddt
import pytest
from django.core.exceptions import ValidationError
from django.test import TestCase
from openedx_ledger.models import Transaction, TransactionStateChoices
from openedx_ledger.test_utils.factories import (
    ExternalFulfillmentProviderFactory,
    ExternalTransactionReferenceFactory,
    TransactionFactory
)
from requests.exceptions import HTTPError
from rest_framework import status

from enterprise_subsidy.apps.content_metadata.constants import ProductSources
from enterprise_subsidy.apps.fulfillment.api import InvalidFulfillmentMetadataException
from enterprise_subsidy.apps.fulfillment.exceptions import IncompleteContentMetadataException
from test_utils.utils import MockResponse

from ..models import ContentNotFoundForCustomerException, PriceValidationError, Subsidy
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

    def tearDown(self):
        super().tearDown()
        self.subsidy.content_metadata_api.reset_mock()

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

    def test_reference_uniqueness(self):
        """
        Tests that not soft-deleted, non-internal-only subsidies
        are validated to be unique on (reference_id, reference_type).
        """
        reference_id = random.randint(1, 10000000)
        existing_record = SubsidyFactory.create(
            enterprise_customer_uuid=self.enterprise_customer_uuid,
            reference_id=reference_id,
            internal_only=False,
        )
        existing_record.save()

        with self.assertRaisesRegex(ValidationError, 'already exists with the same reference_id'):
            new_record = SubsidyFactory.create(
                enterprise_customer_uuid=self.enterprise_customer_uuid,
                reference_id=reference_id,
                internal_only=False,
            )
            new_record.save()

    def test_reference_uniqueness_not_constrained_on_internal_only(self):
        """
        Tests that not soft-deleted, internal-only subsidies
        are allowed to not be unique on (reference_id, reference_type).
        """
        reference_id = random.randint(1, 100000000)
        existing_record = SubsidyFactory.create(
            enterprise_customer_uuid=self.enterprise_customer_uuid,
            reference_id=reference_id,
            internal_only=True,
        )
        existing_record.save()

        new_record = SubsidyFactory.create(
            enterprise_customer_uuid=self.enterprise_customer_uuid,
            reference_id=reference_id,
            internal_only=True,
        )
        new_record.save()
        self.assertEqual(existing_record.reference_id, new_record.reference_id)
        self.assertEqual(existing_record.reference_type, new_record.reference_type)

    def test_reference_uniqueness_not_constrained_when_soft_deleted(self):
        """
        Tests that soft-deleted, non-internal-only subsidies
        are allowed to not be unique on (reference_id, reference_type).
        """
        reference_id = random.randint(1, 100000000)
        existing_record = SubsidyFactory.create(
            enterprise_customer_uuid=self.enterprise_customer_uuid,
            reference_id=reference_id,
            internal_only=False,
            is_soft_deleted=True,
        )
        existing_record.save()

        new_record = SubsidyFactory.create(
            enterprise_customer_uuid=self.enterprise_customer_uuid,
            reference_id=reference_id,
            internal_only=False,
            is_soft_deleted=False,
        )
        new_record.save()
        self.assertEqual(existing_record.reference_id, new_record.reference_id)
        self.assertEqual(existing_record.reference_type, new_record.reference_type)

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

    @ddt.data(True, False)
    def test_is_redeemable_override(self, expected_to_be_redeemable):
        """
        Tests that Subsidy.is_redeemable() returns true when the subsidy
        has enough remaining balance to cover a requested redemption price from the caller,
        and false otherwise.
        """
        # Mock the override price to be slightly too expensive if
        # expected_to_be_redeemable is false;
        # mock it to be slightly affordable if true.
        constant = -123 if expected_to_be_redeemable else 123
        canonical_content_price = self.subsidy.current_balance() + constant
        requested_price = canonical_content_price - 10

        self.subsidy.content_metadata_api().get_course_price.return_value = canonical_content_price

        is_redeemable, price_for_redemption = self.subsidy.is_redeemable('some-content-key', requested_price)

        self.assertEqual(is_redeemable, expected_to_be_redeemable)
        self.assertEqual(requested_price, price_for_redemption)
        self.subsidy.content_metadata_api().get_course_price.assert_called_once_with(
            self.subsidy.enterprise_customer_uuid,
            'some-content-key',
        )

    def test_validate_requested_price_lt_zero(self):
        """
        Requested price validation should fail for requested prices < 0.
        """
        with self.assertRaisesRegex(PriceValidationError, 'non-negative'):
            self.subsidy.validate_requested_price('content-key', -1, 100)

    def test_validate_requested_price_too_high(self):
        """
        Requested price validation should fail for requested prices that are too high
        """
        with self.assertRaisesRegex(PriceValidationError, 'outside of acceptable interval'):
            self.subsidy.validate_requested_price('content-key', 121, 100)

    def test_validate_requested_price_too_low(self):
        """
        Requested price validation should fail for requested prices that are too low
        """
        with self.assertRaisesRegex(PriceValidationError, 'outside of acceptable interval'):
            self.subsidy.validate_requested_price('content-key', 79, 100)

    @ddt.data(80, 120)  # these numbers align exactly to the validation thresholds defined in base settings
    def test_validate_requested_price_just_right(self, requested_price_cents):
        """
        Requested price validation should not fail on requested prices that are just right.
        """
        self.assertEqual(
            self.subsidy.validate_requested_price('content-key', requested_price_cents, 100),
            requested_price_cents,
        )


@ddt.ddt
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
        self.subsidy.lms_user_client = mock.MagicMock()
        self.subsidy.lms_user_client.return_value.best_effort_user_data.return_value = {'email': 'edx@example.com'}
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

    @mock.patch('enterprise_subsidy.apps.subsidy.models.is_geag_fulfillment', return_value=False)
    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content')
    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.enterprise_client')
    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_summary")
    def test_redeem_not_existing(
        self, mock_get_content_summary, mock_enterprise_client,
        mock_price_for_content, mock_is_geag_fulfillment,  # pylint: disable=unused-argument
    ):
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

    @mock.patch('enterprise_subsidy.apps.subsidy.models.is_geag_fulfillment', return_value=False)
    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content')
    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.enterprise_client')
    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_summary")
    def test_redeem_with_requested_price(
        self, mock_get_content_summary, mock_enterprise_client, mock_price_for_content,
        mock_is_geag_fulfillment,  # pylint: disable=unused-argument
    ):
        """
        Test Subsidy.redeem() happy path with an acceptable requested price.
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
            'content_price': 1000,
            'geag_variant_id': None,
        }
        mock_price_for_content.return_value = mock_content_price
        mock_enterprise_client.enroll.return_value = mock_enterprise_fulfillment_uuid
        new_transaction, transaction_created = self.subsidy.redeem(
            lms_user_id,
            content_key,
            subsidy_access_policy_uuid,
            requested_price_cents=990,
        )
        assert transaction_created
        assert new_transaction.state == TransactionStateChoices.COMMITTED
        assert new_transaction.quantity == -990

    @mock.patch('enterprise_subsidy.apps.subsidy.models.is_geag_fulfillment', return_value=False)
    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content')
    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.enterprise_client')
    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_summary")
    def test_redeem_with_requested_price_validation_error(
        self, mock_get_content_summary, mock_enterprise_client, mock_price_for_content,
        mock_is_geag_fulfillment,  # pylint: disable=unused-argument
    ):
        """
        Test Subsidy.redeem() with an unacceptable requested price.
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
            'content_price': 1000,
            'geag_variant_id': None,
        }

        # we'll later assert that no transaction was created during this redemption attempt
        num_txs_before = Transaction.objects.all().count()

        mock_price_for_content.return_value = mock_content_price
        mock_enterprise_client.enroll.return_value = mock_enterprise_fulfillment_uuid
        with self.assertRaisesRegex(PriceValidationError, 'outside of acceptable interval'):
            self.subsidy.redeem(
                lms_user_id,
                content_key,
                subsidy_access_policy_uuid,
                requested_price_cents=500,
            )

        self.assertEqual(num_txs_before, Transaction.objects.all().count())

    @mock.patch('enterprise_subsidy.apps.subsidy.models.is_geag_fulfillment', return_value=False)
    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content')
    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.enterprise_client')
    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_summary")
    def test_redeem_with_metadata(
        self, mock_get_content_summary, mock_enterprise_client, mock_price_for_content,
        mock_is_geag_fulfillment,  # pylint: disable=unused-argument
    ):
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
            'content_title': 'edx: Test Course',
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

    @mock.patch('enterprise_subsidy.apps.subsidy.models.is_geag_fulfillment', return_value=True)
    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content')
    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.enterprise_client')
    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_summary")
    def test_redeem_with_geag_exception(
        self, mock_get_content_summary, mock_enterprise_client, mock_price_for_content,
        mock_is_geag_fulfillment,  # pylint: disable=unused-argument
    ):
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
            'source': ProductSources.TWOU,
            'mode': 'verified',
            'content_price': 10000,
            # When this key value is non-None, it triggers an attempt to create an external fulfillment. This attempt
            # will fail because the metadata below is missing a bunch of required keys, e.g. 'geag_date_of_birth'.
            'geag_variant_id': str(uuid4()),
        }
        mock_price_for_content.return_value = mock_content_price
        mock_enterprise_client.enroll.return_value = mock_enterprise_fulfillment_uuid
        tx_metadata = {
            'geag_first_name': 'Donny',
            'geag_last_name': 'Kerabatsos',
            # The following required keys are missing and will cause external fulfillment to fail.
            # 'geag_email': ,
            # 'geag_date_of_birth': ,
            # 'geag_terms_accepted_at': ,
            # 'geag_data_share_consent': ,
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

    @mock.patch('enterprise_subsidy.apps.subsidy.models.is_geag_fulfillment', return_value=True)
    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content')
    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.enterprise_client')
    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_summary")
    def test_redeem_with_geag_no_variant_id(
        self, mock_get_content_summary, mock_enterprise_client, mock_price_for_content,
        mock_is_geag_fulfillment,  # pylint: disable=unused-argument
    ):
        """
        Test Subsidy.redeem() rollback upon geag validation exception, and enterprise_client not called
        """
        lms_user_id = 1
        content_key = "course-v1:edX+test+course"
        subsidy_access_policy_uuid = str(uuid4())
        mock_content_price = 1000
        mock_get_content_summary.return_value = {
            'content_uuid': 'course-v1:edX+test+course',
            'content_key': 'course-v1:edX+test+course',
            'source': ProductSources.TWOU,
            'mode': 'verified',
            'content_price': 10000,
            'geag_variant_id': None,
        }
        mock_price_for_content.return_value = mock_content_price
        tx_metadata = {
            'geag_first_name': 'Donny',
            'geag_last_name': 'Kerabatsos',
        }
        with pytest.raises(IncompleteContentMetadataException):
            self.subsidy.redeem(
                lms_user_id,
                content_key,
                subsidy_access_policy_uuid,
                metadata=tx_metadata
            )
        created_transaction = Transaction.objects.latest('created')
        assert created_transaction.state == TransactionStateChoices.FAILED
        self.assertFalse(mock_enterprise_client.enroll.called)

    @ddt.data(
        {"cancel_external_fulfillment_side_effect": None},
        {"cancel_external_fulfillment_side_effect": HTTPError()},
        {"cancel_external_fulfillment_side_effect": Exception()},
    )
    @ddt.unpack
    @mock.patch('enterprise_subsidy.apps.subsidy.models.is_geag_fulfillment', return_value=True)
    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content')
    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.enterprise_client')
    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_summary")
    @mock.patch("enterprise_subsidy.apps.api_client.enterprise.EnterpriseApiClient.get_enterprise_customer_data")
    @mock.patch("enterprise_subsidy.apps.fulfillment.api.GEAGFulfillmentHandler._fulfill_in_geag")
    @mock.patch("enterprise_subsidy.apps.fulfillment.api.GEAGFulfillmentHandler.cancel_fulfillment")
    def test_redeem_with_platform_exception_rolls_back_geag(
        self,
        mock_cancel_fulfillment,
        mock_fulfill_in_geag,
        mock_get_enterprise_customer_data,
        mock_get_content_summary,
        mock_enterprise_client,
        mock_price_for_content,
        mock_is_geag_fulfillment,  # pylint: disable=unused-argument
        cancel_external_fulfillment_side_effect,
    ):
        """
        Test Subsidy.redeem() rollback upon platform networking exception handles geag cancellation.
        """
        lms_user_id = 1
        content_key = "course-v1:edX+test+course"
        subsidy_access_policy_uuid = str(uuid4())
        mock_content_price = 1000
        mock_fulfillment_order_uuid = str(uuid4())
        mock_get_content_summary.return_value = {
            'content_uuid': 'course-v1:edX+test+course',
            'content_key': 'course-v1:edX+test+course',
            'source': ProductSources.TWOU,
            'mode': 'verified',
            'content_price': 10000,
            'geag_variant_id': str(uuid4()),
        }
        # Simulate a network failure when attempting to cancel the external fulfillment. The hope is that the
        # transaction should still get rolled back (by progressing to state=failed).
        if cancel_external_fulfillment_side_effect:
            mock_cancel_fulfillment.side_effect = cancel_external_fulfillment_side_effect
        mock_price_for_content.return_value = mock_content_price
        # Create the conditions for a failed platform fulfillment after a successful external fulfillment.
        mock_enterprise_client.enroll.side_effect = HTTPError(
            response=MockResponse(None, status.HTTP_500_INTERNAL_SERVER_ERROR),
        )
        mock_get_enterprise_customer_data.return_value = {}
        mock_fulfill_in_geag.return_value.json.return_value = {
            'orderUuid': mock_fulfillment_order_uuid,
        }
        tx_metadata = {
            'geag_first_name': 'Donny',
            'geag_last_name': 'Kerabatsos',
            'geag_email': 'foo@bar.com',
            'geag_date_of_birth': '1990-01-01',
            'geag_terms_accepted_at': '2024-01-01T00:00:00Z',
            'geag_data_share_consent': True,
        }
        with pytest.raises(HTTPError):
            self.subsidy.redeem(
                lms_user_id,
                content_key,
                subsidy_access_policy_uuid,
                metadata=tx_metadata
            )
        created_transaction = Transaction.objects.latest('created')
        assert created_transaction.state == TransactionStateChoices.FAILED
        # The meat of what's being tested: Did we attempt to cancel the external fulfillment?
        assert mock_cancel_fulfillment.called
        assert mock_cancel_fulfillment.call_args.args[0].external_reference_id == mock_fulfillment_order_uuid


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
