"""
Defines django-filter/DRF FilterSets
for our API views.
"""
from django_filters import filters
from django_filters import rest_framework as drf_filters
from openedx_ledger.models import Transaction, TransactionStateChoices


class HelpfulFilterSet(drf_filters.FilterSet):
    """
    Using an explicit FilterSet object works nicely with drf-spectacular
    for API schema documentation, and injecting the help_text from the model
    field into the filter field causes the help_text value to be rendered
    in the API docs alongside the query parameter names for each filter.

    This implementation is copied from a tip in the django-filter docs:
    https://django-filter.readthedocs.io/en/stable/guide/tips.html#adding-model-field-help-text-to-filters
    """
    @classmethod
    def filter_for_field(cls, field, field_name, lookup_expr=None):
        filter_obj = super(HelpfulFilterSet, cls).filter_for_field(field, field_name, lookup_expr)
        filter_obj.extra['help_text'] = field.help_text
        return filter_obj


class TransactionAdminFilterSet(HelpfulFilterSet):
    """
    Filters for admin transaction list action.
    """
    # It's important that this is filtered as a `MultipleChoiceFilter`,
    # which allows us to specify multiple matching state values
    # in the request query params - this filter type performs an OR
    # by default.
    # https://django-filter.readthedocs.io/en/main/ref/filters.html?highlight=MultipleChoiceFilter#multiplechoicefilter
    state = filters.MultipleChoiceFilter(
        field_name='state',
        choices=TransactionStateChoices.CHOICES,
    )

    class Meta:
        model = Transaction
        fields = [
            'lms_user_id',
            'content_key',
            'subsidy_access_policy_uuid',
            'state',
        ]
