"""
Exceptions for the Fulfillment app
"""


class FulfillmentException(Exception):
    pass


class InvalidFulfillmentMetadataException(FulfillmentException):
    pass


class IncompleteContentMetadataException(FulfillmentException):
    pass
