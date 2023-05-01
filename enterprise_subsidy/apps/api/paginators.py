"""
Customer paginators for the subsidy API.
"""
from rest_framework import pagination

from ..subsidy.models import Subsidy


class TransactionListPaginator(pagination.PageNumberPagination):
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
