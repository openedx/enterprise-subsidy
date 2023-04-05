"""
WORK-IN-PROGRESS

Python API for interacting with fulfillment operations
related to subsidy redemptions.
"""
# pylint: disable=abstract-method,inconsistent-return-statements,no-member
from enterprise_subsidy.apps.api_client.enterprise import EnterpriseApiClient


class FulfillmentHandler:
    """
    Base class for fulfilling a transaction.
    """
    def __init__(self, content_metadata):
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
