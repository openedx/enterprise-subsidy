"""
WORK-IN-PROGRESS

Python API for interacting with fulfillment operations
related to subsidy redemptions.
"""
# pylint: disable=abstract-method,inconsistent-return-statements,no-member
from enterprise_subsidy.apps.api_client.enterprise import EnterpriseApiClient
from django.conf import settings
from getsmarter_api_clients.geag import GetSmarterEnterpriseApiClient

class FulfillmentHandler:
    """
    Base class for fulfilling a transaction.
    """
    def __init__(self, subsidy, content_metadata):
        self.subsidy = subsidy
        self.content_metadata = content_metadata

    def fulfill(self, transaction):
        raise NotImplementedError


class OpenCourseFulfillmentHandler(FulfillmentHandler):
    """
    Creates an Open Course enrollment to fulfill a transaction.
    """
    def enterprise_client(self):
        """
        Get a client for accessing the Enterprise API (edx-enterprise endpoints via edx-platform).
        This contains funcitons used for enrolling learners in OCM courses.
        """
        return EnterpriseApiClient()

    def fulfill(self, transaction):
        reference_id = self.enterprise_client.enroll(
            transaction.lms_user_id,
            transaction.content_key,
        )
        return reference_id


class ExternalFulfillmentHandler(FulfillmentHandler):
    """
    An object to fulfill a transaction.
    """
    def get_client(self):
        pass


class GEAGFulfillmentHandler(ExternalFulfillmentHandler):
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

    def _create_allocation_payload(self, transaction, currency='USD'):
        return {
            'payment_reference': transaction.uuid,
            'enterprise_customer_uuid': self.subsidy.enterprise_customer_uuid,
            'currency': currency,
            'order_items': [
                {
                    # productId will be the variant id from product details
                    'productId': variant_id,
                    'quantity': 1,
                    # TODO what do we do here?
                    # TODO prices are in dollars or cents?
                    'normalPrice': self._get_geag_transaction_price(transaction),
                    'discount': 0.0,
                    'finalPrice': self._get_geag_transaction_price(transaction)
                }
            ],
            'first_name': '',
            'last_name': '',
            'date_of_birth': "2021-05-12",
            'terms_accepted_at': "2021-05-21T17:32:28Z"
        }

    def fulfill(self, transaction):
        # call GEAG client
        # init GEAG client
        # allocation_id = geag_client.allocate(...)
        # enterprise_client.enroll(...)
        # return allocation_id, edx_fulfillment_uuid, maybe?
        # but then also do an enroll in edx-enterprise
        # maybe via a sub-OpenCourseFulfillmentHandler?
        pass


class FulfillmentManager:
    """
    Manager for creating an appropriate handler
    and storing any log-level facts about the fulfillment attempt.
    """


def get_fulfillment_handlers(content_metadata):
    """
    Could implement this as multiple fulfillment operations, but all on a single
    transaction record to fulfill.
    """
    if content_metadata.get('product_source') == 'the-twou-product-source':
        return [GEAGFulfillmentHandler(content_metadata), OpenCourseFulfillmentHandler(content_metadata)]
