"""
Module to define API Exceptions that we return.
"""
from rest_framework import status
from rest_framework.exceptions import APIException


class ErrorCodes:
    """
    Defines a few standard API error codes.
    """
    ENROLLMENT_ERROR = 'enrollment_error'
    CONTENT_NOT_FOUND = 'content_not_found'
    INVALID_REQUESTED_PRICE = 'invalid_requested_price'
    TRANSACTION_CREATION_ERROR = 'transaction_creation_error'
    DEPOSIT_CREATION_ERROR = 'deposit_creation_error'
    LEDGER_LOCK_ERROR = 'ledger_lock_error'
    INACTIVE_SUBSIDY_CREATION_ERROR = 'inactive_subsidy_creation_error'
    FULFILLMENT_ERROR = 'fulfillment_error'


class SubsidyAPIException(APIException):
    """
    Custom API exception class allowing for overriding the status code and exposing the error code.
    """
    status_code = None
    default_detail = None
    default_code = None

    def __init__(self, detail=None, code=None, status_code=None):
        """
        This exception can override the default status_code
        and also ensures that the error code makes its way
        into the detail of the response.  `detail` will
        always be returns as a dict.
        """
        super().__init__(detail=detail, code=code)
        if status_code:
            self.status_code = status_code
        if not isinstance(self.detail, dict):
            self.detail = {'detail': self.detail}
        self.detail['code'] = code or self.default_code


class TransactionCreationAPIException(SubsidyAPIException):
    """
    Custom exception raised when transactions cannot be created.
    """
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = 'Error creating transaction.'
    default_code = ErrorCodes.TRANSACTION_CREATION_ERROR


class DepositCreationAPIException(SubsidyAPIException):
    """
    Custom exception raised when Deposits cannot be created.
    """
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = 'Error creating deposit.'
    default_code = ErrorCodes.DEPOSIT_CREATION_ERROR
