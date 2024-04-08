"""
Common exceptions related to Transactions.
"""


class TransactionException(Exception):
    """
    Base exception class around transactions.
    """


class TransactionFulfillmentCancelationException(TransactionException):
    """
    Raised when a Transaction cannot be unfulfilled (un-enrolled).
    """
