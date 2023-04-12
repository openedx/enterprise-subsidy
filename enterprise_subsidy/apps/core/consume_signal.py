import logging

from django.dispatch import receiver

from openedx_events.learning.signals import (
    COURSE_ENROLLMENT_CREATED,
    COURSE_ENROLLMENT_CHANGED,
    COURSE_UNENROLLMENT_COMPLETED
)


@receiver(COURSE_ENROLLMENT_CREATED)
def new_enrollment_created(**kwargs):
    """
    When an enrollment is created, log a statement.

    Args:
        kwargs: event data sent to signal
    """

    logging.info('Received "COURSE_ENROLLMENT_CREATED" event: %s', kwargs)
    logging.info('Just log the enrollment_id: %s', kwargs['enrollment'].user)
