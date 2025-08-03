"""
Tests for Transaction utils.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import ddt
from django.test import TestCase
from opaque_keys.edx.locator import CourseLocator
from openedx_ledger.test_utils.factories import LedgerFactory, TransactionFactory

from enterprise_subsidy.apps.transaction.utils import unenrollment_can_be_refunded


@ddt.ddt
class TransactionUtilsTestCase(TestCase):
    """
    Tests for Transaction utils.
    """

    @ddt.data(
        # ALMOST non-refundable due to transaction_created_at.
        {
            "transaction_created_at": datetime(2020, 1, 10, tzinfo=ZoneInfo("UTC")),
            "course_start_date": datetime(2020, 1, 1, tzinfo=ZoneInfo("UTC")),
            "unenrolled_at": datetime(2020, 1, 23, tzinfo=ZoneInfo("UTC")),
            "expected_refundable": True,
        },
        # Non-refundable due to transaction_created_at.
        {
            "transaction_created_at": datetime(2020, 1, 10, tzinfo=ZoneInfo("UTC")),
            "course_start_date": datetime(2020, 1, 1, tzinfo=ZoneInfo("UTC")),
            "unenrolled_at": datetime(2020, 1, 24, tzinfo=ZoneInfo("UTC")),
            "expected_refundable": False,
        },
        # ALMOST non-refundable due to course_start_date.
        {
            "transaction_created_at": datetime(2020, 1, 1, tzinfo=ZoneInfo("UTC")),
            "course_start_date": datetime(2020, 1, 10, tzinfo=ZoneInfo("UTC")),
            "unenrolled_at": datetime(2020, 1, 23, tzinfo=ZoneInfo("UTC")),
            "expected_refundable": True,
        },
        # Non-refundable due to course_start_date.
        {
            "transaction_created_at": datetime(2020, 1, 1, tzinfo=ZoneInfo("UTC")),
            "course_start_date": datetime(2020, 1, 10, tzinfo=ZoneInfo("UTC")),
            "unenrolled_at": datetime(2020, 1, 24, tzinfo=ZoneInfo("UTC")),
            "expected_refundable": False,
        },
    )
    @ddt.unpack
    def test_unenrollment_can_be_refunded_courserun(
        self,
        transaction_created_at,
        course_start_date,
        unenrolled_at,
        expected_refundable,
    ):
        """
        Make sure the following formula is respected:

        MAX(transaction_created_at, course_start_date) + 14 days > unenrolled_at
        """
        test_content_metadata = {
            "content_type": "courserun",
            "start": course_start_date.strftime('%Y-%m-%dT%H:%M:%SZ'),
        }
        test_enterprise_course_enrollment = {
            "unenrolled_at": unenrolled_at,
        }
        transaction = TransactionFactory(ledger=LedgerFactory())
        transaction.created = transaction_created_at
        transaction.save()

        assert unenrollment_can_be_refunded(
            test_content_metadata,
            test_enterprise_course_enrollment,
            transaction,
        ) == expected_refundable

    @ddt.data(
        # ALMOST non-refundable due to transaction_created_at.
        {
            "transaction_created_at": datetime(2020, 1, 10, tzinfo=ZoneInfo("UTC")),
            "course_start_date": datetime(2020, 1, 1, tzinfo=ZoneInfo("UTC")),
            "unenrolled_at": datetime(2020, 1, 23, tzinfo=ZoneInfo("UTC")),
            "expected_refundable": True,
        },
        # Non-refundable due to transaction_created_at.
        {
            "transaction_created_at": datetime(2020, 1, 10, tzinfo=ZoneInfo("UTC")),
            "course_start_date": datetime(2020, 1, 1, tzinfo=ZoneInfo("UTC")),
            "unenrolled_at": datetime(2020, 1, 24, tzinfo=ZoneInfo("UTC")),
            "expected_refundable": False,
        },
        # ALMOST non-refundable due to course_start_date.
        {
            "transaction_created_at": datetime(2020, 1, 1, tzinfo=ZoneInfo("UTC")),
            "course_start_date": datetime(2020, 1, 10, tzinfo=ZoneInfo("UTC")),
            "unenrolled_at": datetime(2020, 1, 23, tzinfo=ZoneInfo("UTC")),
            "expected_refundable": True,
        },
        # Non-refundable due to course_start_date.
        {
            "transaction_created_at": datetime(2020, 1, 1, tzinfo=ZoneInfo("UTC")),
            "course_start_date": datetime(2020, 1, 10, tzinfo=ZoneInfo("UTC")),
            "unenrolled_at": datetime(2020, 1, 24, tzinfo=ZoneInfo("UTC")),
            "expected_refundable": False,
        },
    )
    @ddt.unpack
    def test_unenrollment_can_be_refunded_course(
        self,
        transaction_created_at,
        course_start_date,
        unenrolled_at,
        expected_refundable,
    ):
        """
        Make sure the following formula is respected:

        MAX(transaction_created_at, course_start_date) + 14 days > unenrolled_at
        """
        test_content_metadata = {
            "content_type": "course",
            "course_runs": [
                {
                    "key": "course-v1:bin+bar+baz",
                    "start": course_start_date.strftime('%Y-%m-%dT%H:%M:%SZ'),
                },
            ],
        }
        test_enterprise_course_enrollment = {
            "unenrolled_at": unenrolled_at,
            "course_id": CourseLocator("bin", "bar", "baz", None, None),
        }
        transaction = TransactionFactory(ledger=LedgerFactory())
        transaction.created = transaction_created_at
        transaction.save()
        assert unenrollment_can_be_refunded(
            test_content_metadata,
            test_enterprise_course_enrollment,
            transaction,
        ) == expected_refundable
