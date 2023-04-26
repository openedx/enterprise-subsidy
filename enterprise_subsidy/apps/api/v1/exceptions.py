"""
Custom exceptions for the Subsidy API
"""
from rest_framework.exceptions import APIException


class ServerError(APIException):
    """
    A custom exception class for server errors.
    This class is a subclass of the DRF APIException class, and is designed
    to be raised when an unexpected error occurs in the subsidies service.
    """
    status_code = 500
    default_detail = 'encountered an unexpected error in subsidies service'
    default_code = 'server_error'

    def __init__(self, *args, **kwargs):
        self.code = kwargs['code']
        self.developer_message = kwargs.pop('developer_message', None)
        self.user_message = kwargs.pop('user_message', None)
        super().__init__(*args, **kwargs)
