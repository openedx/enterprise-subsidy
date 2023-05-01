"""
Python API for interacting with fulfillment operations
related to subsidy redemptions.
"""
# pylint: disable=unused-import
from enterprise_subsidy.apps.content_metadata import api as content_metadata_api

from .constants import EXEC_ED_2U_COURSE_TYPES, OPEN_COURSES_COURSE_TYPES

from django.conf import settings
from enterprise_subsidy.apps.content_metadata.api import ContentMetadataApi
from getsmarter_api_clients.geag import GetSmarterEnterpriseApiClient

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
    CENTS_PER_DOLLAR = 100.0

    def get_smarter_client(self):
        return GetSmarterEnterpriseApiClient(
            client_id=settings.GET_SMARTER_OAUTH2_KEY,
            client_secret=settings.GET_SMARTER_OAUTH2_SECRET,
            provider_url=settings.GET_SMARTER_OAUTH2_PROVIDER_URL,
            api_url=settings.GET_SMARTER_API_URL
        )

    def _get_geag_transaction_price(self, transaction):
        return float(transaction.quantity) / self.CENTS_PER_DOLLAR

    def _get_enterprise_customer_uuid(self, transaction):
        return transaction.ledger.subsidy.enterprise_customer_uuid

    def _get_geag_variant_id(self, transaction):
        ent_uuid = self._get_enterprise_customer_uuid(transaction)
        return ContentMetadataApi().get_geag_variant_id(ent_uuid, transaction.content_key)

    def _create_allocation_payload(self, transaction, currency='USD'):
        transaction_price = self._get_geag_transaction_price(transaction)
        return {
            'payment_reference': transaction.uuid,
            'enterprise_customer_uuid': self.subsidy.enterprise_customer_uuid,
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
            'date_of_birth': transaction.metadata.get('geag_date_of_birth'),
            'terms_accepted_at': transaction.metadata.get('geag_terms_accepted_at'),
        }

    def _validate(self, transaction):
        """
        Validates that a ledger transaction contains all the required information to
        construct a GEAG allocation payload.

        Raises an exception when the transaction is missing required information
        """
        for field in ['geag_first_name', 'geag_last_name', 'geag_date_of_birth', 'geag_terms_accepted_at']:
            if not transaction.metadata.get(field):
                # TODO make this a proper exception class
                raise f'missing {field} transaction metadata'

    def can_fulfill(self, transaction):
        """
        A helper to let callers know if the transaction at hand can be fulfilled
        with this fulfillment handler.
        """
        return self._get_geag_variant_id(transaction)

    def fulfill(self, transaction):
        """
        Attempt to fulfill a ledger transaction with the GEAG fulfillment system
        """
        self._validate(transaction)
        allocation_payload = self._create_allocation_payload(transaction)
        geag_response = self.get_smarter_client(**allocation_payload)
        return geag_response.json().get('orderUuid')
