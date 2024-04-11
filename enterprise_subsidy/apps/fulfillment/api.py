"""
Python API for interacting with fulfillment operations
related to subsidy redemptions.
"""
import logging

from django.conf import settings
from getsmarter_api_clients.geag import GetSmarterEnterpriseApiClient
from openedx_ledger.models import ExternalFulfillmentProvider, ExternalTransactionReference
from requests.exceptions import HTTPError

# pylint: disable=unused-import
from enterprise_subsidy.apps.content_metadata import api as content_metadata_api
from enterprise_subsidy.apps.content_metadata.api import ContentMetadataApi
from enterprise_subsidy.apps.core.utils import request_cache, versioned_cache_key
from enterprise_subsidy.apps.subsidy.constants import CENTS_PER_DOLLAR

from .constants import EXEC_ED_2U_COURSE_TYPES, OPEN_COURSES_COURSE_TYPES
from .exceptions import FulfillmentException, InvalidFulfillmentMetadataException

REQUEST_CACHE_NAMESPACE = 'enterprise_data'
logger = logging.getLogger(__name__)


def create_fulfillment(subsidy_uuid, lms_user_id, content_key, **metadata):
    """
    Creates a fulfillment.
    """
    raise NotImplementedError


def determine_fulfillment_client(subsidy_uuid, content_key):
    """
    Function stub.
    Determines which API client can fulfill a redemption for the given content_key.
    The implementation will likely want to follow a pattern like this:

    metadata = content_metadata_api.get_content_metadata(content_key)
    course_type = metadata.get('course_type')
    if course_type in EXEC_ED_2U_COURSE_TYPES:
        # really we need to return an exec-ed-capable client
        return None
    if course_type in OPEN_COURSES_COURSE_TYPES:
        # return an edx-enterprise client
        return None
    return None
    """
    raise NotImplementedError


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

    def _get_enterprise_customer_uuid(self, transaction):
        return transaction.ledger.subsidy.enterprise_customer_uuid

    def _get_geag_variant_id(self, transaction):
        ent_uuid = self._get_enterprise_customer_uuid(transaction)
        return ContentMetadataApi().get_geag_variant_id(ent_uuid, transaction.content_key)

    def _get_enterprise_customer_data(self, transaction):
        """
        Fetches and caches enterprise customer data based on a transaction.
        """
        cache_key = versioned_cache_key(
            'get_enterprise_customer_data',
            self._get_enterprise_customer_uuid(transaction),
            transaction.uuid,
        )
        # Check if data is already cached
        cached_response = request_cache(namespace=REQUEST_CACHE_NAMESPACE).get_cached_response(cache_key)
        if cached_response.is_found:
            return cached_response.value
        # If data is not cached, fetch and cache it
        enterprise_customer_uuid = str(self._get_enterprise_customer_uuid(transaction))
        ent_client = self.get_enterprise_client(transaction)
        enterprise_data = ent_client.get_enterprise_customer_data(enterprise_customer_uuid)

        request_cache(namespace=REQUEST_CACHE_NAMESPACE).set(cache_key, enterprise_data)

        return enterprise_data

    def _get_auth_org_id(self, transaction):
        return self._get_enterprise_customer_data(transaction).get('auth_org_id')

    def _create_allocation_payload(self, transaction, currency='USD'):
        # TODO: come back an un-hack this once GEAG validation is
        # more fully understood.
        transaction_price = self._get_geag_transaction_price(transaction)
        return {
            'payment_reference': str(transaction.uuid),
            'enterprise_customer_uuid': str(self._get_enterprise_customer_uuid(transaction)),
            'currency': currency,
            'order_items': [
                {
                    # productId will be the variant id from product details
                    'productId': self._get_geag_variant_id(transaction),
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

    def fulfill(self, transaction):
        """
        Attempt to fulfill a ledger transaction with the GEAG fulfillment system
        """
        self._validate(transaction)
        allocation_payload = self._create_allocation_payload(transaction)
        geag_response = self._fulfill_in_geag(allocation_payload)
        response_payload = geag_response.json()

        try:
            geag_response.raise_for_status()
            external_reference_id = response_payload.get('orderUuid')
            if not external_reference_id:
                raise FulfillmentException('missing orderUuid / external_reference_id from geag')
            logger.info(
                '[transaction fulfillment] Fulfilled transaction %s with external reference id %s',
                transaction.uuid,
                external_reference_id,
            )
            return self._save_fulfillment_reference(transaction, external_reference_id)
        except HTTPError as exc:
            raise FulfillmentException(response_payload.get('errors') or geag_response.text) from exc

    def cancel_fulfillment(self, external_transaction_reference):
        """
        Cancels the provided external reference's (related to some ``Transaction`` record)
        related enterprise allocation.
        """
        self.get_smarter_client().cancel_enterprise_allocation(
            external_transaction_reference.external_reference_id,
        )
        logger.info(
            '[transaction fulfillment] Cancelled fulfillment for transaction %s with external reference id %s',
            external_transaction_reference.transaction.uuid,
            external_transaction_reference.external_reference_id,
        )
