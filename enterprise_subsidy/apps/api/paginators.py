"""
Customer paginators for the subsidy API.
"""
from math import ceil

from edx_rest_framework_extensions.paginators import DefaultPagination
from rest_framework import pagination

from ..subsidy.models import Subsidy


class TransactionListPaginator(DefaultPagination):
    """
    Optionally adds an `aggregates` dictionary to the base pagination response
    of transaction list views.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.subsidy = None
        self.total_quantity = None

    def paginate_queryset(self, queryset, request, view=None):
        """
        Assumes that `queryset` is based on transaction records,
        and that we want an aggregate quantity computed from those records.
        Requires that the view class defines a `requested_subsidy_uuid` property.
        """
        if request.query_params.get("include_aggregates", "").lower() == "true":
            self.subsidy = Subsidy.objects.get(uuid=view.requested_subsidy_uuid)
            self.total_quantity = self.subsidy.ledger.subset_balance(queryset)
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data):
        """
        Optionally inserts a top-level `aggregates` dictionary into the base paginated response.
        """
        paginated_response = super().get_paginated_response(data)
        if self.total_quantity is not None:
            aggregates = {
                "unit": self.subsidy.unit,
                "remaining_subsidy_balance": self.subsidy.current_balance(),
                "total_quantity": self.total_quantity,
            }
            paginated_response.data['aggregates'] = aggregates
        return paginated_response


class SubsidyListPaginator(pagination.PageNumberPagination):
    """
    Adds a computer 'page_count' number to the base pagination response
    of subsidy list views.
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.page_count = None
        self.pagination_page_size = None

    def paginate_queryset(self, queryset, request, view=None):
        """
        Assigns 'pagination_page_size' the page size from the request parameter
        or the default paginator value
        """
        self.pagination_page_size = int(request.query_params.get('page_size', self.page_size))
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data):
        """
        Adds an attribute of page_count to be used for the support-tools subsidy table
        """
        paginated_response = super().get_paginated_response(data)
        paginated_response.data['page_count'] = ceil(paginated_response.data['count'] / self.pagination_page_size)
        return paginated_response
