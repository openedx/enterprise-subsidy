"""
Utility functions used in the implementation of subsidy Transactions.
"""
import logging
from datetime import datetime, timedelta

from django.db.models import Q

logger = logging.getLogger(__name__)


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


def normalize_to_datetime(datetime_or_str):
    """
    Given a datetime or ISO timestamp string, always return a datetime object.
    """
    try:
        parsed_dt = datetime.fromisoformat(datetime_or_str)
    except TypeError:
        parsed_dt = datetime_or_str
    return parsed_dt


def unenrollment_can_be_refunded(
    content_metadata,
    enterprise_course_enrollment,
):
    """
    Helper method to determine if an unenrollment is refundable.

    Args:
      content_metadata (dict): Metadata for course from which the learner has been unenrolled.
      enterprise_course_enrollment: (dict):
        Serialized ECE object. If the caller has an instance of
        openedx_events.enterprise.data.EnterpriseCourseEnrollment, coerce to
        data object first: `ece_record.__dict__`

    """
    # Retrieve the course start date from the content metadata
    enrollment_course_run_key = str(enterprise_course_enrollment.get("course_id"))
    course_start_date = None
    if content_metadata.get('content_type') == 'courserun':
        course_start_date = content_metadata.get('start')
    else:
        for run in content_metadata.get('course_runs', []):
            if run.get('key') == enrollment_course_run_key:
                course_start_date = run.get('start')
                break

    if not course_start_date:
        logger.warning(
            f"No course start date found for course run: {enrollment_course_run_key}. "
            "Unable to determine refundability."
        )
        return False

    # https://2u-internal.atlassian.net/browse/ENT-6825
    # OCM course refundability is defined as True IFF:
    # ie MAX(enterprise enrollment created at, course start date) + 14 days > unenrolled_at date
    enrollment_created_datetime = normalize_to_datetime(enterprise_course_enrollment.get("created"))
    enrollment_unenrolled_at_datetime = normalize_to_datetime(enterprise_course_enrollment.get("unenrolled_at"))
    course_start_datetime = normalize_to_datetime(course_start_date)
    refund_cutoff_date = max(course_start_datetime, enrollment_created_datetime) + timedelta(days=14)
    if refund_cutoff_date > enrollment_unenrolled_at_datetime:
        logger.info(
            f"Course run: {enrollment_course_run_key} is refundable for enterprise customer user: "
            f"{enterprise_course_enrollment.get('enterprise_customer_user')}. Writing Reversal record."
        )
        return True
    else:
        logger.info(
            f"Unenrollment from course: {enrollment_course_run_key} by user: "
            f"{enterprise_course_enrollment.get('enterprise_customer_user')} is not refundable."
        )
        return False
