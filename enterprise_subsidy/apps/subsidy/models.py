"""
Model definitions for the subsidy app.
"""
from datetime import datetime
from functools import lru_cache
from unittest import mock
from uuid import uuid4

from pytz import UTC

from django.db import models, transaction
from model_utils.models import TimeStampedModel

from openedx_ledger import api as ledger_api
from openedx_ledger.utils import create_idempotency_key_for_transaction
from openedx_ledger.models import Ledger, UnitChoices


MOCK_GROUP_CLIENT = mock.MagicMock()
MOCK_CATALOG_CLIENT = mock.MagicMock()
MOCK_ENROLLMENT_CLIENT = mock.MagicMock()
MOCK_SUBSCRIPTION_CLIENT = mock.MagicMock()
MOCK_SUBSIDY_REQUESTS_CLIENT = mock.MagicMock()

CENTS_PER_DOLLAR = 100


def now():
    return UTC.localize(datetime.utcnow())


class Subsidy(TimeStampedModel):
    """
    Some defintions:
    ``ledger``: A running “list” of transactions that record the movement of value in and out of a subsidy.
    ``stored value``: Value, in the form of a subscription license (denominated in “seats”)
        or learner credit (denominated in either USD or "seats"), stored in a ledger,
        which may be applied toward the cost of some content.
    ``redemption``: The act of redeeming stored value for content.
    """
    class Meta:
        """
        Metaclass for Subsidy.
        """
        abstract = True

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid4,
        editable=False,
        unique=True,
    )
    # `title` is required for downstream revenue recognition.  The intention is to serve as a replacement to "offer
    # name" in the old system.
    title = models.CharField(
        max_length=255,
        blank=False,
        null=False,
    )
    starting_balance = models.BigIntegerField(
        null=False, blank=False,
    )
    ledger = models.ForeignKey(Ledger, null=True, on_delete=models.SET_NULL)
    unit = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        choices=UnitChoices.CHOICES,
        default=UnitChoices.USD_CENTS,
        db_index=True,
    )
    opportunity_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )
    customer_uuid = models.UUIDField(
        blank=False,
        null=False,
        db_index=True,
    )

    active_datetime = models.DateTimeField(null=True, default=None)
    expiration_datetime = models.DateTimeField(null=True, default=None)

    @property
    def catalog_client(self):
        return MOCK_CATALOG_CLIENT

    @property
    def subsidy_requests_client(self):
        return MOCK_SUBSIDY_REQUESTS_CLIENT

    def current_balance(self):
        return self.ledger.balance()

    def create_transaction(self, idempotency_key, quantity, metadata):
        return ledger_api.create_transaction(
            ledger=self.ledger,
            quantity=quantity,
            idempotency_key=idempotency_key,
            metadata=metadata,
        )

    def commit_transaction(self, ledger_transaction, reference_id):
        ledger_transaction.reference_id = reference_id
        ledger_transaction.save()

    def rollback_transaction(self, ledger_transaction):
        # delete it, or set some state?
        pass

    def redeem(self, learner_id, content_key, **kwargs):
        """
        Redeem this subsidy and enroll the learner.
        """
        if redemption := self.has_redeemed(learner_id, content_key, **kwargs):
            return redemption

        if not self.is_redeemable(content_key, now()):
            return None

        return self._create_redemption(learner_id, content_key, **kwargs)

    def _create_redemption(self, learner_id, content_key, **kwargs):
        raise NotImplementedError

    def request_redemption(self, learner_id, content_key, **kwargs):
        if _request := self.has_requested(learner_id, content_key):
            return _request

        return self._create_request(learner_id, content_key, **kwargs)

    def _create_request(self, learner_id, content_key, **kwargs):
        raise NotImplementedError

    def is_redeemable(self, content_key, redemption_datetime=None):
        """
        Is there enough stored value in this subsidy's ledger to redeem for the cost
        (denominated in the unit of this subsidy) of the given content?
        """
        raise NotImplementedError

    def has_redeemed(self, learner_id, content_key, **kwargs):
        raise NotImplementedError

    def has_requested(self, learner_id, content_key):
        raise NotImplementedError

    def all_transactions(self):
        return self.ledger.transactions

    def transactions_for_learner(self, lms_user_id):
        return self.all_transactions().filter(lms_user_id=lms_user_id)

    def transactions_for_content(self, content_uuid):
        return self.all_transactions().filter(content_uuid=content_uuid)

    def transactions_for_learner_and_content(self, lms_user_id, content_uuid):
        return self.all_transactions().filter(
            lms_user_id=lms_user_id,
            content_uuid=content_uuid,
        )


class LearnerCreditSubsidy(Subsidy):
    """
    A subsidy model for Learner Credit/bucket of money.

    .. no_pii:
    """
    @property
    def enrollment_client(self):
        return MOCK_ENROLLMENT_CLIENT

    @lru_cache(maxsize=128)
    def price_for_content(self, content_key):
        return self.catalog_client.get_content_metadata(content_key).get('price') * CENTS_PER_DOLLAR

    def is_redeemable(self, content_key, redemption_datetime=None):
        return self.current_balance() >= self.price_for_content(content_key)

    def has_redeemed(self, learner_id, content_key, **kwargs):
        return self.transactions_for_learner_and_content(learner_id, content_key)

    def _create_redemption(self, learner_id, content_key, **kwargs):
        """
        Actual enrollment happens downstream of this.
        commit a transaction here.
        """
        transaction_metadata = {
            'content_key': content_key,
            'learner_id': learner_id,
        }

        quantity = self.price_for_content(content_key)

        idempotency_key = create_idempotency_key_for_transaction(
            self,
            quantity,
            learner_id=learner_id,
            content_key=content_key,
        )
        ledger_transaction = self.create_transaction(
            idempotency_key,
            quantity * -1,
            transaction_metadata,
        )

        try:
            reference_id = self.enrollment_client.enroll(learner_id, content_key, ledger_transaction)
            self.commit_transaction(ledger_transaction, reference_id)
        except Exception as exc:
            self.rollback_transaction(ledger_transaction)
            raise exc

        return ledger_transaction

    def _create_request(self, learner_id, content_key, **kwargs):
        """
        TODO: need a hook from enterprise-access that tells the subsidy
        when a request has been approved, so that we can _create_redemption()
        on the subsidy.
        Additionally, we'd want a hook for request denials to avoid duplicating
        work, etc.
        """
        return self.subsidy_requests_client.request_learner_credit(learner_id, content_key)

    def has_requested(self, learner_id, content_key):
        return self.subsidy_requests_client.get_learner_credit_requests(
            learner_id,
            content_key,
        )


class SubscriptionSubsidy(Subsidy):
    """
    A subsidy backed by a subscription.

    Currently subscriptions licenses are tracked in a separate IDA (license-manager) rather than internal models,
    and as such does not make use of a ledger.

    .. no_pii:
    """
    subscription_plan_uuid = models.UUIDField(null=False, blank=False, db_index=True)

    class Meta:
        """
        Metaclass for SubscriptionSubsidy.
        """
        # The choice of what a subsidy is unique on dictates behavior
        # that we can implement around the lifecycle of the subsidy.
        # For instance, making this type of subsidy unique on the (customer, plan id, unit)
        # means that every renewal or roll-over of a plan must result in a new plan id.
        unique_together = []

    @property
    def subscription_client(self):
        """
        Return an API client for the subscription service.
        """
        MOCK_SUBSCRIPTION_CLIENT.create_license.return_value = uuid4()
        MOCK_SUBSCRIPTION_CLIENT.get_license.return_value = {
            'uuid': uuid4(),
            'status': 'activated',
        }
        return MOCK_SUBSCRIPTION_CLIENT

    def _is_license_available(self):
        """
        Check that there are available licenses in the current subscription plan.
        """
        plan_metadata = self.subscription_client.get_plan_metadata(
            self.subscription_plan_uuid,
        )
        return plan_metadata['licenses']['pending'] > 0

    def _get_license_for_learner(self, learner_id):
        return self.subscription_client.get_license(
            self.subscription_plan_uuid,
            learner_id,
        )

    def _assign_license(self, learner_id, **kwargs):
        """
        Calls an subscription API client to grant a license as a redemption
        for this subsidy.
        """
        # Note: licenses are created when the plan is created
        # so we're not creating a new one, here.
        license_metadata = self.subscription_client.assign_license(
            self.subscription_plan_uuid,
            learner_id,
        )
        return license_metadata

    def has_redeemed(self, learner_id, content_key, **kwargs):
        return self._get_license_for_learner(learner_id)

    def is_redeemable(self, content_key, redemption_datetime=None):
        return self._is_license_available()

    def _create_redemption(self, learner_id, content_key, **kwargs):
        """
        For subscription subsidies, a redemption is either the fact that the
        learner is already assigned a license for the plan, or the result
        of assigning an available license to the learner.
        """
        return self._assign_license(learner_id)

    def _create_request(self, learner_id, content_key, **kwargs):
        return self.subsidy_requests_client.request_license(learner_id)

    def has_requested(self, learner_id, content_key):
        return self.subsidy_requests_client.get_license_requests(
            learner_id,
            content_key,
        )


class AccessMethods:
    DIRECT = 'direct'
    REQUEST = 'request'


class SubsidyAccessPolicy(TimeStampedModel):
    """
    Tie together information used to control access to a subsidy.

    This abstract model joins group, catalog, and access method.  Subclasses must define a `subsidy` field, and may
    include additional relationships as needed.
    """
    class Meta:
        """
        Metaclass for SubsidyAccessPolicy.
        """
        abstract = True

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid4,
        editable=False,
        unique=True,
    )
    group_uuid = models.UUIDField(null=True, blank=True, db_index=True)
    catalog_uuid = models.UUIDField(null=True, blank=True, db_index=True)
    access_method = AccessMethods.DIRECT

    @property
    def group_client(self):
        """
        Return an API client for the groups service.
        """
        return MOCK_GROUP_CLIENT

    @classmethod
    def get_policies_for_groups(cls, group_uuids):
        """
        Fetch all the policies that are related to the given groups.
        """
        return cls.objects.filter(group_uuid__in=group_uuids)

    @property
    def catalog_client(self):
        """
        Return an API client for the enterprise-catalog service.
        """
        return MOCK_CATALOG_CLIENT

    def is_entitled(self, learner_id, content_key):
        """
        Check that a given learner is entitled to enroll in the given content.
        """
        if not self.catalog_client.catalog_contains_content(self.catalog_uuid, content_key):
            return False
        if not self.group_client.group_contains_learner(self.group_uuid, learner_id):
            return False
        if not self.subsidy.is_redeemable(content_key):  # pylint: disable=no-member
            return False
        return True

    def redeem_entitlement(self, learner_id, content_key):
        """
        Redeem an entitlement for the given learner and content.

        Returns:
            A ledger transaction, or None if the entitlement was not redeemed.
        """
        if self.is_entitled(learner_id, content_key):
            if self.access_method == AccessMethods.DIRECT:
                return self.subsidy.redeem(learner_id, content_key)
            if self.access_method == AccessMethods.REQUEST:
                return self.subsidy.request_redemption(learner_id, content_key)
        return None

    def has_redeemed_entitlement(self, learner_id, content_key):
        if self.access_method == AccessMethods.DIRECT:
            return self.subsidy.has_redeemed(learner_id, content_key)  # pylint: disable=no-member
        elif self.access_method == AccessMethods.REQUEST:
            return self.subsidy.has_requested(learner_id, content_key)
        else:
            raise ValueError(f"unknown access method {self.access_method}")


class SubscriptionAccessPolicy(SubsidyAccessPolicy):
    """
    A subsidy access policy for subscriptions (all you can eat).

    .. no_pii:
    """
    subsidy = models.ForeignKey(SubscriptionSubsidy, null=True, on_delete=models.SET_NULL)


class LearnerCreditAccessPolicy(SubsidyAccessPolicy):
    """
    A subsidy access policy for learner credit.

    .. no_pii:
    """
    subsidy = models.ForeignKey(LearnerCreditSubsidy, null=True, on_delete=models.SET_NULL)


class PerLearnerEnrollmentCapLearnerCreditAccessPolicy(LearnerCreditAccessPolicy):
    """
    Example policy that limits the number of enrollments (really) transactions
    that a learner is entitled to in a subsidy.

    .. no_pii:
    """
    per_learner_cap = models.IntegerField(
        blank=True,
        default=0,
    )

    def is_entitled(self, learner_id, content_key):
        with transaction.atomic():
            if self.subsidy.transactions_for_learner(learner_id).count() < self.per_learner_cap:
                return super().is_entitled(learner_id, content_key)
            else:
                return False


class LicenseRequestAccessPolicy(SubscriptionAccessPolicy):
    """
    A subsidy access policy for license request.

    .. no_pii:
    """
    access_method = AccessMethods.REQUEST
