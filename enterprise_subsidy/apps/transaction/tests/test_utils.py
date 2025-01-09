"""
Tests for Transaction utils.
"""
from datetime import datetime

import ddt
from django.test import TestCase
from opaque_keys.edx.locator import CourseLocator
from pytz import UTC

from enterprise_subsidy.apps.transaction.signals.handlers import unenrollment_can_be_refunded


@ddt.ddt
class TransactionUtilsTestCase(TestCase):
    """
    Tests for Transaction utils.
    """

    @ddt.data(
        # ALMOST non-refundable due to enterprise_enrollment_created_at.
        {
            "enterprise_enrollment_created_at": datetime(2020, 1, 10, tzinfo=UTC),
            "course_start_date": datetime(2020, 1, 1, tzinfo=UTC),
            "unenrolled_at": datetime(2020, 1, 23, tzinfo=UTC),
            "expected_refundable": True,
        },
        # Non-refundable due to enterprise_enrollment_created_at.
        {
            "enterprise_enrollment_created_at": datetime(2020, 1, 10, tzinfo=UTC),
            "course_start_date": datetime(2020, 1, 1, tzinfo=UTC),
            "unenrolled_at": datetime(2020, 1, 24, tzinfo=UTC),
            "expected_refundable": False,
        },
        # ALMOST non-refundable due to course_start_date.
        {
            "enterprise_enrollment_created_at": datetime(2020, 1, 1, tzinfo=UTC),
            "course_start_date": datetime(2020, 1, 10, tzinfo=UTC),
            "unenrolled_at": datetime(2020, 1, 23, tzinfo=UTC),
            "expected_refundable": True,
        },
        # Non-refundable due to course_start_date.
        {
            "enterprise_enrollment_created_at": datetime(2020, 1, 1, tzinfo=UTC),
            "course_start_date": datetime(2020, 1, 10, tzinfo=UTC),
            "unenrolled_at": datetime(2020, 1, 24, tzinfo=UTC),
            "expected_refundable": False,
        },
    )
    @ddt.unpack
    def test_unenrollment_can_be_refunded_courserun(
        self,
        enterprise_enrollment_created_at,
        course_start_date,
        unenrolled_at,
        expected_refundable,
    ):
        """
        Make sure the following forumla is respected:

        MAX(enterprise_enrollment_created_at, course_start_date) + 14 days > unenrolled_at
        """
        test_content_metadata = {
            "content_type": "courserun",
            "start": course_start_date.strftime('%Y-%m-%dT%H:%M:%SZ'),
        }
        test_enterprise_course_enrollment = {
            "created": enterprise_enrollment_created_at,
            "unenrolled_at": unenrolled_at,
        }
        assert unenrollment_can_be_refunded(
            test_content_metadata,
            test_enterprise_course_enrollment,
        ) == expected_refundable

    @ddt.data(
        # ALMOST non-refundable due to enterprise_enrollment_created_at.
        {
            "enterprise_enrollment_created_at": datetime(2020, 1, 10, tzinfo=UTC),
            "course_start_date": datetime(2020, 1, 1, tzinfo=UTC),
            "unenrolled_at": datetime(2020, 1, 23, tzinfo=UTC),
            "expected_refundable": True,
        },
        # Non-refundable due to enterprise_enrollment_created_at.
        {
            "enterprise_enrollment_created_at": datetime(2020, 1, 10, tzinfo=UTC),
            "course_start_date": datetime(2020, 1, 1, tzinfo=UTC),
            "unenrolled_at": datetime(2020, 1, 24, tzinfo=UTC),
            "expected_refundable": False,
        },
        # ALMOST non-refundable due to course_start_date.
        {
            "enterprise_enrollment_created_at": datetime(2020, 1, 1, tzinfo=UTC),
            "course_start_date": datetime(2020, 1, 10, tzinfo=UTC),
            "unenrolled_at": datetime(2020, 1, 23, tzinfo=UTC),
            "expected_refundable": True,
        },
        # Non-refundable due to course_start_date.
        {
            "enterprise_enrollment_created_at": datetime(2020, 1, 1, tzinfo=UTC),
            "course_start_date": datetime(2020, 1, 10, tzinfo=UTC),
            "unenrolled_at": datetime(2020, 1, 24, tzinfo=UTC),
            "expected_refundable": False,
        },
    )
    @ddt.unpack
    def test_unenrollment_can_be_refunded_course(
        self,
        enterprise_enrollment_created_at,
        course_start_date,
        unenrolled_at,
        expected_refundable,
    ):
        """
        Make sure the following forumla is respected:

        MAX(enterprise_enrollment_created_at, course_start_date) + 14 days > unenrolled_at
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
            "created": enterprise_enrollment_created_at,
            "unenrolled_at": unenrolled_at,
            "course_id": CourseLocator("bin", "bar", "baz", None, None),
        }
        assert unenrollment_can_be_refunded(
            test_content_metadata,
            test_enterprise_course_enrollment,
        ) == expected_refundable
