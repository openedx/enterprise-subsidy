"""
Utility functions used in the implementation of subsidy Transactions.
"""

from django.db.models import Q


def generate_transaction_reversal_idempotency_key(fulfillment_uuid, enrollment_unenrolled_at):
    """
    Generates a unique idempotency key for a transaction reversal using the fulfillment uuid and time at which the
    unenrollment occurred.
    """
    return f'unenrollment-reversal-{fulfillment_uuid}-{enrollment_unenrolled_at}'


def batch_by_pk(ModelClass, extra_filter=Q(), batch_size=10000):
    """
    yield per batch efficiently
    using limit/offset does a lot of table scanning to reach higher offsets
    this scanning can be slow on very large tables
    if you order by pk, you can use the pk as a pivot rather than offset
    this utilizes the index, which is faster than scanning to reach offset
    Example usage:
    filter_query = Q(column='value')
    for items_batch in batch_by_pk(Model, extra_filter=filter_query):
        for item in items_batch:
            ...
    """
    qs = ModelClass.objects.filter(extra_filter).order_by('pk')[:batch_size]
    while qs.exists():
        yield qs
        # qs.last() doesn't work here because we've already sliced
        # loop through so we eventually grab the last one
        for item in qs:
            start_pk = item.pk
        qs = ModelClass.objects.filter(pk__gt=start_pk).filter(extra_filter).order_by('pk')[:batch_size]
