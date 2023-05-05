"""
Tests for functions defined in the ``api.py`` module.
"""
from unittest import mock
from uuid import uuid4

import pytest
from django.test import TestCase
from openedx_ledger.models import TransactionStateChoices
from openedx_ledger.test_utils.factories import TransactionFactory

from enterprise_subsidy.apps.fulfillment.api import GEAGFulfillmentHandler, InvalidFulfillmentMetadataException
from enterprise_subsidy.apps.subsidy.tests.factories import SubsidyFactory


class GEAGFulfillmentHandlerTestCase(TestCase):
    """
    Test GEAGFulfillmentHandler
    """
    def setUp(self):
        self.geag_fulfillment_handler = GEAGFulfillmentHandler()
        self.enterprise_customer_uuid = uuid4()
        self.subsidy_access_policy_uuid = uuid4()
        self.subsidy = SubsidyFactory.create(
            enterprise_customer_uuid=self.enterprise_customer_uuid,
            starting_balance=100000,
        )
        self.subsidy.content_metadata_api = mock.MagicMock()
        self.subsidy.content_metadata_api().get_course_price.return_value = 19998
        self.lms_user_id = 42
        self.content_key = 'some-content-key'
        super().setUp()

    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_summary")
    def test_can_fulfill_ocm(self, mock_get_content_summary):
        """
        Ensure basic happy path of `can_fulfill` for OCM (cannot fulfill)
        """
        mock_get_content_summary.return_value = {
            'content_uuid': 'course-v1:edX-test-course',
            'content_key': 'course-v1:edX-test-course',
            'source': 'edX',
            'mode': 'verified',
            'content_price': 10000,
            'geag_variant_id': None,
        }
        transaction = TransactionFactory.create(
            state=TransactionStateChoices.PENDING,
            quantity=-19998,
            ledger=self.subsidy.ledger,
            lms_user_id=self.lms_user_id,
            content_key=self.content_key
        )
        assert not self.geag_fulfillment_handler.can_fulfill(transaction)

    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_summary")
    def test_can_fulfill_geag(self, mock_get_content_summary):
        """
        Ensure basic happy path of `can_fulfill` for Exec Ed (can fulfill)
        """
        mock_get_content_summary.return_value = {
            'content_uuid': 'course-v1:edX-test-course',
            'content_key': 'course-v1:edX-test-course',
            'source': 'edX',
            'mode': 'verified',
            'content_price': 10000,
            'geag_variant_id': uuid4(),
        }
        transaction = TransactionFactory.create(
            state=TransactionStateChoices.PENDING,
            quantity=-19998,
            ledger=self.subsidy.ledger,
            lms_user_id=self.lms_user_id,
            content_key=self.content_key
        )
        assert self.geag_fulfillment_handler.can_fulfill(transaction)

    def test_save_reference(self):
        """
        Ensure basic happy path of `_save_fulfillment_reference`
        """
        transaction = TransactionFactory.create(
            state=TransactionStateChoices.PENDING,
            quantity=-19998,
            ledger=self.subsidy.ledger,
            lms_user_id=self.lms_user_id,
            content_key=self.content_key
        )
        external_reference_id = uuid4()
        # pylint: disable=protected-access
        external_transaction_reference = self.geag_fulfillment_handler._save_fulfillment_reference(
            transaction,
            external_reference_id
        )
        assert external_transaction_reference
        assert external_transaction_reference.external_reference_id == external_reference_id
        this_slug = external_transaction_reference.external_fulfillment_provider.slug
        assert this_slug == self.geag_fulfillment_handler.EXTERNAL_FULFILLMENT_PROVIDER_SLUG

    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_summary")
    def test_create_allocation_payload(self, mock_get_content_summary):
        """
        Ensure basic happy path of `_create_allocation_payload`
        """
        content_summary = {
            'content_uuid': 'course-v1:edX-test-course',
            'content_key': 'course-v1:edX-test-course',
            'source': 'edX',
            'mode': 'verified',
            'content_price': 10000,
            'geag_variant_id': str(uuid4()),
        }
        mock_get_content_summary.return_value = content_summary
        tx_metadata = {
            'geag_first_name': 'Donny',
            'geag_last_name': 'Kerabatsos',
            'geag_email': 'donny@example.com',
            'geag_date_of_birth': '1900-01-01',
            'geag_terms_accepted_at': '2021-05-21T17:32:28Z',
            'geag_data_share_consent': True,
        }
        transaction = TransactionFactory.create(
            state=TransactionStateChoices.PENDING,
            quantity=-19998,
            ledger=self.subsidy.ledger,
            lms_user_id=self.lms_user_id,
            content_key=self.content_key,
            metadata=tx_metadata,
        )
        # pylint: disable=protected-access
        geag_payload = self.geag_fulfillment_handler._create_allocation_payload(transaction)
        assert geag_payload.get('payment_reference') == str(transaction.uuid).replace('-', '')[:20]
        assert geag_payload.get('order_items')[0].get('productId') == content_summary.get('geag_variant_id')
        for payload_field in self.geag_fulfillment_handler.REQUIRED_METADATA_FIELDS:
            geag_field = payload_field[len('geag_'):]
            if payload_field == 'geag_data_share_consent':
                assert geag_payload.get(geag_field) == 'true'
            else:
                assert geag_payload.get(geag_field) == tx_metadata.get(payload_field)

    def test_validate_pass(self):
        """
        Ensure `_validate` method passes
        """
        tx_metadata = {
            'geag_first_name': 'Donny',
            'geag_last_name': 'Kerabatsos',
            'geag_email': 'donny@example.com',
            'geag_date_of_birth': '1900-01-01',
            'geag_terms_accepted_at': '2021-05-21T17:32:28Z',
            'geag_data_share_consent': True,
        }
        transaction = TransactionFactory.create(
            state=TransactionStateChoices.PENDING,
            quantity=-19998,
            ledger=self.subsidy.ledger,
            lms_user_id=self.lms_user_id,
            content_key=self.content_key,
            metadata=tx_metadata,
        )
        # pylint: disable=protected-access
        assert self.geag_fulfillment_handler._validate(transaction)

    def test_validate_fail(self):
        """
        Ensure `_validate` method raises with a missing `geag_terms_accepted_at`
        """
        tx_metadata = {
            'geag_first_name': 'Donny',
            'geag_last_name': 'Kerabatsos',
            'geag_email': 'donny@example.com',
            'geag_date_of_birth': '1900-01-01',
            'geag_terms_accepted_at': '2021-05-21T17:32:28Z',
            'geag_data_share_consent': True,
        }
        transaction = TransactionFactory.create(
            state=TransactionStateChoices.PENDING,
            quantity=-19998,
            ledger=self.subsidy.ledger,
            lms_user_id=self.lms_user_id,
            content_key=self.content_key,
            metadata=tx_metadata,
        )
        # validate that removing any of the required fields results in an exception
        for field in self.geag_fulfillment_handler.REQUIRED_METADATA_FIELDS:
            transaction.metadata = {k: v for k, v in tx_metadata.items() if k != field}
            with pytest.raises(InvalidFulfillmentMetadataException):
                # pylint: disable=protected-access
                self.geag_fulfillment_handler._validate(transaction)

    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_summary")
    @mock.patch("enterprise_subsidy.apps.fulfillment.api.GEAGFulfillmentHandler._fulfill_in_geag")
    def test_fulfill(self, mock_fulfill_in_geag, mock_get_content_summary):
        """
        Ensure basic happy path of `fulfill`
        """
        content_summary = {
            'content_uuid': 'course-v1:edX-test-course',
            'content_key': 'course-v1:edX-test-course',
            'source': 'edX',
            'mode': 'verified',
            'content_price': 10000,
            'geag_variant_id': str(uuid4()),
        }
        mock_get_content_summary.return_value = content_summary
        geag_response = {
            'orderUuid': str(uuid4()),
        }
        mock_fulfill_in_geag.return_value = geag_response
        tx_metadata = {
            'geag_first_name': 'Donny',
            'geag_last_name': 'Kerabatsos',
            'geag_email': 'donny@example.com',
            'geag_date_of_birth': '1900-01-01',
            'geag_terms_accepted_at': '2021-05-21T17:32:28Z',
            'geag_data_share_consent': True,
        }
        transaction = TransactionFactory.create(
            state=TransactionStateChoices.PENDING,
            quantity=-19998,
            ledger=self.subsidy.ledger,
            lms_user_id=self.lms_user_id,
            content_key=self.content_key,
            metadata=tx_metadata,
        )
        external_transaction_reference = self.geag_fulfillment_handler.fulfill(transaction)
        assert external_transaction_reference
        assert external_transaction_reference.transaction == transaction
        this_slug = external_transaction_reference.external_fulfillment_provider.slug
        assert this_slug == self.geag_fulfillment_handler.EXTERNAL_FULFILLMENT_PROVIDER_SLUG
        assert external_transaction_reference.external_reference_id == geag_response.get('orderUuid')
