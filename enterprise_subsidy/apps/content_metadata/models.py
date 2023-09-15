"""
Models for the content_metadata app.
"""
from datetime import timedelta

from django.db import models
from django.utils import timezone
from django_extensions.db.models import TimeStampedModel
from simple_history.models import HistoricalRecords


FRESHNESS_THRESHOLD = timedelta(days=7)


class RecentlyModifiedManager(models.Manager):
    def get_queryset(self):
        threshold_point = timezone.now() - FRESHNESS_THRESHOLD
        return super().get_queryset().filter(
            modified__gte=threshold_point,
        )


class ReplicatedContentMetadata(TimeStampedModel):
    """
    Let this thing have a BigAutoField PK - ``uuid`` would be too overloaded.
    """
    class Meta:
        # Let's have at most one record per (customer, content key) combination.
        # side-note: modeling it like this means we're replicating not just
        # content metadtata, but also catalog inclusion, which I think is a
        # nice side effect to have going forward.
        unique_together = [
            ('enterprise_customer_uuid', 'content_key'),
        ]

    enterprise_customer_uuid = models.UUIDField(
        null=False,
        blank=False,
        editable=False,
        db_index=True,
    )
    content_key = models.CharField(
        max_length=255,
        editable=False,
        null=False,
        blank=False,
        db_index=True,
        help_text=(
            "The globally unique content identifier for this course.  Joinable with "
            "ContentMetadata.content_key in enterprise-catalog."
        ),
    )
    content_type = models.CharField(
        max_length=255,
        null=False,
        db_index=True,
        help_text="The type of content (e.g. course or courserun).",
    )
    raw_metadata = models.JSONField(
        null=False,
        blank=False,
        help_text="The raw JSON metadata fetched from the enterprise-catalog customer metadata API.",
    )
    raw_fetched_at = models.DateTimeField(
        null=False,
        blank=False,
        editable=False,
        help_text="Time at which raw_metadata was last fetched.",
    )
    title = models.CharField(
        max_length=2047,
        null=True,
        help_text="The title of the course",
    )
    price = models.BigIntegerField(
        null=False,
        blank=False,
        help_text="Cost of this course run in USD Cents.",
    )
    product_source = models.CharField(
        max_length=255,
        null=True,
        db_index=True,
        help_text="The product source for this course.",
    )
    course_mode = models.CharField(
        max_length=255,
        null=True,
        db_index=True,
        help_text="The enrollment mode supported for this course.",
    )
    history = HistoricalRecords()

    objects = models.Manager()
    recent_objects = RecentlyModifiedManager()

    @classmethod
    def get_recent_record_or_null(cls, enterprise_customer_uuid, content_key):
        try:
            return cls.recent_objects.get(
                enterprise_customer_uuid=enterprise_customer_uuid,
                content_key=content_key,
            )
        except cls.DoesNotExist:
            return None
