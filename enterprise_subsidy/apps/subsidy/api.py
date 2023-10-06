"""
The python API.
"""

from enterprise_subsidy.apps.subsidy.models import RevenueCategoryChoices, Subsidy


def get_or_create_learner_credit_subsidy(
    reference_id,
    default_title,
    default_enterprise_customer_uuid,
    default_active_datetime,
    default_expiration_datetime,
    default_unit,
    default_starting_balance,
    default_revenue_category=RevenueCategoryChoices.BULK_ENROLLMENT_PREPAY,
    default_internal_only=False,
):
    """
    Get or create a new learner credit subsidy and ledger with the given defaults.

    Notes:
        * If ``default_internal_only`` is False and an existing subsidy is
          found with the given ``reference_id``, all `default_*` arguments are ignored
          and this function returns that existing record.
          However, when ``default_internal_only`` is True, this function will
          simply create a new record, regardless of any existing records
          with the same ``reference_id`` (we assume that the reference_id is
          essentially meaningless for test subsidy records).

    Args:
        reference_id (str): ID of the originating salesforce opportunity product.
        default_title (str): Human-readable title of the new subsidy.
        default_enterprise_customer_uuid (uuid.UUID): UUID of the enterprise customer.
        default_unit (str):
            Value unit identifier of the new subsidy (choices defined in openedx_ledger.models.UnitChoices).
        default_starting_balance (int): The starting balance of the new subsidy.
        default_revenue_category (str, optional, default bulk-enrollment-prepay):
            Revenue category slug (choices defined in enterprise_subsidy.apps.subsidy.models.RevenueCategoryChoices).
        default_internal_only (bool, optional, default False): Set to true to make this subsidy only internal-facing.

    Returns:
        tuple(enterprise_subsidy.apps.subsidy.models.Subsidy, bool):
            The subsidy record, and an bool that is true if a new subsidy+ledger was created.
    """
    subsidy_defaults = {
        'title': default_title,
        'starting_balance': default_starting_balance,
        'enterprise_customer_uuid': default_enterprise_customer_uuid,
        'active_datetime': default_active_datetime,
        'expiration_datetime': default_expiration_datetime,
        'unit': default_unit,
        'revenue_category': default_revenue_category,
        'internal_only': default_internal_only,
    }
    if not default_internal_only:
        subsidy, created = Subsidy.objects.get_or_create(
            reference_id=reference_id,
            defaults=subsidy_defaults,
        )
    else:
        # The record to create is for testing, do a plain ole create()
        created = True
        subsidy = Subsidy.objects.create(
            reference_id=reference_id,
            **subsidy_defaults,
        )
    return (subsidy, created)


def get_subsidy_by_uuid(subsidy_uuid, should_raise=False):
    """
    Params:
      subsidy_uuid: The uuid of the Subsidy record to fetch.

    Returns:
      A Subsidy instance, or null if no such subsidy exists.
    """
    try:
        return Subsidy.objects.get(uuid=subsidy_uuid)
    except Subsidy.DoesNotExist:
        if should_raise:
            raise
        return None


def can_redeem(subsidy, lms_user_id, content_key):
    """
    Determines if the given learner can redeem against the
    provided subsidy for the given content_key.

    Params:
      subsidy: The Subsidy record against which redeemability is queried.
      lms_user_id: (int) Primary (edX LMS) identifier of the learner for whom
        the redeemability query is being made.
      content_key: (string) The content key of content for which
        the redeemability query is being made.

    Returns:
      3-tuple of (
        boolean: whether the user can redeem.
        int: price of content.
        list of Transaction: all current and historical redemptions/transactions for user+content.
      )
    """
    existing_transaction = subsidy.get_committed_transaction_no_reversal(lms_user_id, content_key)
    is_active = subsidy.is_active
    if existing_transaction:
        is_redeemable = False
        price_for_content = subsidy.price_for_content(content_key)
    else:
        is_redeemable, price_for_content = subsidy.is_redeemable(content_key)
    all_transactions_for_learner_and_content = list(
        subsidy.transactions_for_learner_and_content(lms_user_id, content_key)
    )
    return (is_redeemable, is_active, price_for_content, all_transactions_for_learner_and_content)
