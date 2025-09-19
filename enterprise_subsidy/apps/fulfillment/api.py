"""
Python API for interacting with fulfillment operations
related to subsidy redemptions.
"""
import logging

from django.conf import settings
from getsmarter_api_clients.geag import GetSmarterEnterpriseApiClient
from openedx_ledger.models import ExternalFulfillmentProvider, ExternalTransactionReference
from requests.exceptions import HTTPError

from enterprise_subsidy.apps.content_metadata.api import ContentMetadataApi
from enterprise_subsidy.apps.content_metadata.constants import ProductSources
from enterprise_subsidy.apps.core.utils import request_cache, versioned_cache_key
from enterprise_subsidy.apps.subsidy.constants import CENTS_PER_DOLLAR

from .constants import FALLBACK_EXTERNAL_REFERENCE_ID_KEY
from .exceptions import FulfillmentException, IncompleteContentMetadataException, InvalidFulfillmentMetadataException

GEAG_DUPLICATE_ORDER_ERROR_CODE = 10174
REQUEST_CACHE_NAMESPACE = 'enterprise_data'
logger = logging.getLogger(__name__)


def create_fulfillment(subsidy_uuid, lms_user_id, content_key, **metadata):
    """
    Creates a fulfillment.
    """
    raise NotImplementedError


def get_customer_uuid(transaction):
    return transaction.ledger.subsidy.enterprise_customer_uuid


def is_geag_fulfillment(transaction):
    """
    Returns whether the given transaction's content metadata is of the 2u/GEAG type (which is
    to say - executive education).
    """
    ent_uuid = get_customer_uuid(transaction)
    product_source = ContentMetadataApi().get_product_source(ent_uuid, transaction.content_key)
    result = product_source == ProductSources.TWOU.value
    logger.info('Transaction %s is_geag_fulfillment=%s', transaction.uuid, result)
    return result


class GEAGFulfillmentHandler():
    """
    A class for fulfilling a GEAG transaction.
    """
    EXTERNAL_FULFILLMENT_PROVIDER_SLUG = 'geag'
    REQUIRED_METADATA_FIELDS = [
        'geag_first_name',
        'geag_last_name',
        'geag_email',
        'geag_date_of_birth',
        'geag_terms_accepted_at',
        'geag_data_share_consent',
    ]

    def get_smarter_client(self):
        return GetSmarterEnterpriseApiClient(
            client_id=settings.GET_SMARTER_OAUTH2_KEY,
            client_secret=settings.GET_SMARTER_OAUTH2_SECRET,
            provider_url=settings.GET_SMARTER_OAUTH2_PROVIDER_URL,
            api_url=settings.GET_SMARTER_API_URL
        )

    def get_enterprise_client(self, transaction):
        return transaction.ledger.subsidy.enterprise_client

    def _get_geag_transaction_price(self, transaction):
        """
        Get the price in dollars to send to GEAG from transaction quantities,
        which are decrements (thus negative) and in cents
        """
        return -1.0 * (float(transaction.quantity) / CENTS_PER_DOLLAR)

    def _get_geag_variant_id(self, transaction):
        """
        Get the geag_variant_id from the metadata API, or raise a fatal exception if not found.
        """
        ent_uuid = get_customer_uuid(transaction)
        geag_variant_id = ContentMetadataApi().get_geag_variant_id(ent_uuid, transaction.content_key)
        return geag_variant_id

    def _get_enterprise_customer_data(self, transaction):
        """
        Fetches and caches enterprise customer data based on a transaction.
        """
        cache_key = versioned_cache_key(
            'get_enterprise_customer_data',
            get_customer_uuid(transaction),
            transaction.uuid,
        )
        # Check if data is already cached
        cached_response = request_cache(namespace=REQUEST_CACHE_NAMESPACE).get_cached_response(cache_key)
        if cached_response.is_found:
            return cached_response.value
        # If data is not cached, fetch and cache it
        enterprise_customer_uuid = str(get_customer_uuid(transaction))
        ent_client = self.get_enterprise_client(transaction)
        enterprise_data = ent_client.get_enterprise_customer_data(enterprise_customer_uuid)

        request_cache(namespace=REQUEST_CACHE_NAMESPACE).set(cache_key, enterprise_data)

        return enterprise_data

    def _get_auth_org_id(self, transaction):
        return self._get_enterprise_customer_data(transaction).get('auth_org_id')

    def _create_allocation_payload(self, transaction, currency='USD'):
        """
        Construct a payload sent to GEAG to create an enterprise allocation.

        Raises:
          - IncompleteContentMetadataException:
                If the requested content is not Exec Ed, or content metadata has missing data for some reason.
        """
        # TODO: come back an un-hack this once GEAG validation is
        # more fully understood.
        transaction_price = self._get_geag_transaction_price(transaction)
        variant_id = self._get_geag_variant_id(transaction)
        if not variant_id:
            raise IncompleteContentMetadataException(
                f'Missing variant_id needed to construct an allocation payload for transaction {transaction}'
            )
        return {
            'payment_reference': str(transaction.uuid),
            'enterprise_customer_uuid': str(get_customer_uuid(transaction)),
            'currency': currency,
            'order_items': [
                {
                    # productId will be the variant id from product details
                    'productId': variant_id,
                    'quantity': 1,
                    'normalPrice': transaction_price,
                    'discount': 0.0,
                    'finalPrice': transaction_price,
                }
            ],
            'first_name': transaction.metadata.get('geag_first_name'),
            'last_name': transaction.metadata.get('geag_last_name'),
            'email': transaction.metadata.get('geag_email'),
            'date_of_birth': transaction.metadata.get('geag_date_of_birth'),
            'terms_accepted_at': transaction.metadata.get('geag_terms_accepted_at'),
            'data_share_consent': str(transaction.metadata.get('geag_data_share_consent', 'true')).lower(),
            'org_id': self._get_auth_org_id(transaction),
        }

    def _validate(self, transaction):
        """
        Validates that a ledger transaction contains all the required information to
        construct a GEAG allocation payload.

        Raises an exception when the transaction is missing required information
        """
        enterprise_customer_data = self._get_enterprise_customer_data(transaction)
        enable_data_sharing_consent = enterprise_customer_data.get('enable_data_sharing_consent', False)
        for field in self.REQUIRED_METADATA_FIELDS:
            if field == 'geag_data_share_consent' and not enable_data_sharing_consent:
                continue
            if not transaction.metadata.get(field):
                raise InvalidFulfillmentMetadataException(f'missing {field} transaction metadata')
        return True

    def _save_fulfillment_reference(self, transaction, external_reference_id):
        external_fulfillment_provider, _ = ExternalFulfillmentProvider.objects.get_or_create(
            slug=self.EXTERNAL_FULFILLMENT_PROVIDER_SLUG
        )
        return ExternalTransactionReference.objects.create(
            transaction=transaction,
            external_fulfillment_provider=external_fulfillment_provider,
            external_reference_id=external_reference_id,
        )

    def can_fulfill(self, transaction):
        """
        A helper to let callers know if the transaction at hand can be fulfilled
        with this fulfillment handler.
        """
        return bool(self._get_geag_variant_id(transaction))

    def _fulfill_in_geag(self, allocation_payload):
        """
        Calls the `create_enterprise_allocation` endpoint via the GEAG client.
        """
        geag_response = self.get_smarter_client().create_enterprise_allocation(
            **allocation_payload,
            should_raise=False,
        )
        return geag_response

    def fulfill(self, transaction) -> ExternalTransactionReference:
        """
        Attempt to fulfill a ledger transaction with the GEAG fulfillment system

        Returns:
            ExternalTransactionReference: A new ExternalTransactionReference representing the new external fulfillment.
        """
        self._validate(transaction)
        logger.info('Beginning external fulfillment for transaction %s', transaction.uuid)
        allocation_payload = self._create_allocation_payload(transaction)
        geag_response = self._fulfill_in_geag(allocation_payload)
        response_payload = geag_response.json()
        logger.info('Transaction %s has GEAG response payload: %s', transaction.uuid, response_payload)

        try:
            geag_response.raise_for_status()
        except HTTPError as exc:
            errors = response_payload.get('errors')
            if errors and errors[0].get('code') == GEAG_DUPLICATE_ORDER_ERROR_CODE:
                logger.info(
                    '[transaction fulfillment] Discovered an already existing GEAG fulfillment. Full response payload: '
                    f'{geag_response.text}'
                )
            else:
                raise FulfillmentException(errors or geag_response.text) from exc

        # Find the orderUuid by looking in multiple places.
        external_reference_id = (
            # First, prioritize looking inside the response payload. This is the most
            # direct and authoritative source. However, if the request failed on
            # "duplicate order", we can't rely on this key being available, but support
            # the case where it is made available in the future.
            response_payload.get('orderUuid')
            # Second, look in the transaction metadata where it's possible the
            # ForcedPolicyRedemption flow has set a fallback value.
            or transaction.metadata.get(FALLBACK_EXTERNAL_REFERENCE_ID_KEY)
        )
        if not external_reference_id:
            raise FulfillmentException('missing orderUuid / external_reference_id from geag')
        logger.info(
            '[transaction fulfillment] Fulfilled transaction %s with external reference id %s',
            transaction.uuid,
            external_reference_id,
        )

        return self._save_fulfillment_reference(transaction, external_reference_id)

    def cancel_fulfillment(self, external_transaction_reference):
        """
        Cancels the provided external reference's (related to some ``Transaction`` record)
        related enterprise allocation.

        Raises:
            HTTPError:
                Calling the external platform API to cancel an external fulfillment failed. Currently, this could happen
                if the external reference does not refer to a GEAG fulfillment because we currently only support GEAG
                external fulfillments.
        """
        self.get_smarter_client().cancel_enterprise_allocation(
            external_transaction_reference.external_reference_id,
        )
        logger.info(
            '[transaction fulfillment] Cancelled fulfillment for transaction %s with external reference id %s',
            external_transaction_reference.transaction.uuid,
            external_transaction_reference.external_reference_id,
        )
