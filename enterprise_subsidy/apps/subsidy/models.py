"""
Model definitions for the subsidy app.

Some defintions:
* `ledger`: A running “list” of transactions that record the movement of value in and out of a subsidy.
* `stored value`:
      Value, in the form of a subscription license (denominated in “seats”) or learner credit (denominated in either
      USD or "seats"), stored in a ledger, which may be applied toward the cost of some content.
* `redemption`: The act of redeeming stored value for content.
"""
from datetime import datetime, timezone
from functools import lru_cache
from unittest import mock
from uuid import uuid4

from django.db import models
from edx_rbac.models import UserRole, UserRoleAssignment
from edx_rbac.utils import ALL_ACCESS_CONTEXT
from model_utils.models import TimeStampedModel
from openedx_ledger import api as ledger_api
from openedx_ledger.models import Ledger, UnitChoices
from openedx_ledger.utils import create_idempotency_key_for_transaction
from simple_history.models import HistoricalRecords

MOCK_CATALOG_CLIENT = mock.MagicMock()
MOCK_ENROLLMENT_CLIENT = mock.MagicMock()
MOCK_SUBSCRIPTION_CLIENT = mock.MagicMock()

CENTS_PER_DOLLAR = 100


class SubsidyReferenceChoices:
    """
    Enumerate different choices for a subsidy originator ID.

    The originator is the object that caused the subsidy to come into existence.  Currently, the only such object is the
    "product" inside the Salesforce opportunity.
    """
    OPPORTUNITY_PRODUCT_ID = 'opportunity_product_id'
    CHOICES = (
        (OPPORTUNITY_PRODUCT_ID, 'Opportunity Product ID'),
    )


def now():
    return datetime.now(timezone.utc)


class Subsidy(TimeStampedModel):
    """
    Subsidy model, specifically supporting Learner Credit type of subsidies.

    TODO: need a hook from enterprise-access that tells the subsidy when a request has been approved, so that we can
          _create_redemption() on the subsidy.  Additionally, we'd want a hook for request denials to avoid duplicating
          work, etc.

    .. no_pii:
    """

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid4,
        editable=False,
        unique=True,
    )
    # `title` can be useful for downstream revenue recognition, and for a more convenient identifier.  It is intended to
    # be provided by ECS during the process of creating the Subsidy object.
    title = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )
    starting_balance = models.BigIntegerField(
        null=False, blank=False,
    )
    ledger = models.OneToOneField(Ledger, null=True, on_delete=models.SET_NULL)
    unit = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        choices=UnitChoices.CHOICES,
        default=UnitChoices.USD_CENTS,
        db_index=True,
    )
    reference_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )
    reference_type = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        choices=SubsidyReferenceChoices.CHOICES,
        default=SubsidyReferenceChoices.OPPORTUNITY_PRODUCT_ID,
        db_index=True,
    )
    enterprise_customer_uuid = models.UUIDField(
        blank=False,
        null=False,
        db_index=True,
    )

    internal_only = models.BooleanField(
        blank=False,
        null=False,
        default=False
    )

    active_datetime = models.DateTimeField(null=True, default=None)
    expiration_datetime = models.DateTimeField(null=True, default=None)
    history = HistoricalRecords()

    @property
    def enrollment_client(self):
        """
        TODO: implement enrollment client
        """
        return MOCK_ENROLLMENT_CLIENT

    @property
    def catalog_client(self):
        return MOCK_CATALOG_CLIENT

    @lru_cache(maxsize=128)
    def price_for_content(self, content_key):
        return self.catalog_client.get_content_metadata(content_key).get("price") * CENTS_PER_DOLLAR

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

    def redeem(self, learner_id, content_key):
        """
        Redeem this subsidy and enroll the learner.

        This is a get_or_create type of function, so it is idempotent.  It also checks if the the content is redeemable
        by the learner.

        Returns:
            openedx_ledger.models.Transaction: a ledger transaction related to the redemption.
        """
        if redemption := self.get_redemption(learner_id, content_key):
            return redemption

        if not self.is_redeemable(content_key, now()):
            return None

        return self._create_redemption(learner_id, content_key)

    def _create_redemption(self, learner_id, content_key, **kwargs):
        """
        Synchronously and idempotently enroll the learner in the content and record it in the Ledger.

        Two side-effects:
        * An enrollment or an entitlement is created in the target system (with metadata that links back to the ledger
          transaction ID).  The learner is able to access the requested content.
        * A Transaction is created in the Ledger associated with this subsidy, with state set to `committed` (and a
          reference_id set to the enrollment_id).

        After this function returns, either both of the two side-effects are fulfilled, *or neither*.

        Possible failure cases:
        * The enrollment fails to become created, returning a non-2xx error back to the subsidy service.  We should not
          commit a ledger transaction, but it's not outside the realm of possibilities that the enrollment has been
          *partially provisioned* in the target LMS. A partially provisioned enrollment is acceptable as long as the
          content remains inaccessible, and it can still be re-provisioned idempotently.
        * The enrollment succeeds, links a ledger transaction ID, returns a 2xx response to the subsidy app, but before
          the app receives the response, either the network connection is interrupted, or the subsidy app crashes.  This
          failure mode must be remedied asynchronously via corrective policies:
          https://github.com/openedx/enterprise-subsidy/blob/main/docs/decisions/0003-fulfillment-and-corrective-policies.rst#decision

        Bi-directional linking: Subclass implementations MUST also maintain bi-directional linking between the
        transaction record and the enrollment record.  The Transaction model provides a `reference_id` field for this
        purpose.
        """
        transaction_metadata = {
            "content_key": content_key,
            "learner_id": learner_id,
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

    def is_redeemable(self, content_key, redemption_datetime=None):  # pylint: disable=unused-argument
        """
        Check if this subsidy is redeemable (by anyone) at a given time.

        Is there enough stored value in this subsidy's ledger to redeem for the cost of the given content?
        TODO: Also take into account redemption_datetime.

        Args:
            content_key (str): content key of content we may try to redeem.
            redemption_datetime (datetime.datetime): The point in time to check for redemability.

        Returns:
            bool: True if redeemable.
        """
        return self.current_balance() >= self.price_for_content(content_key)

    def get_redemption(self, learner_id, content_key):
        """
        Return the transaction representing this redemption, if it exists.

        Args:
            learner_id (str): The learner of the redemption to check.
            content_key (str): The content of the redemption to check.

        Returns:
            openedx_ledger.models.Transaction: a ledger transaction related to the redemption.
        """
        return self.transactions_for_learner_and_content(learner_id, content_key)

    def all_transactions(self):
        return self.ledger.transactions  # pylint: disable=no-member

    def transactions_for_learner(self, lms_user_id):
        return self.all_transactions().filter(lms_user_id=lms_user_id)

    def transactions_for_content(self, content_uuid):
        return self.all_transactions().filter(content_uuid=content_uuid)

    def transactions_for_learner_and_content(self, lms_user_id, content_uuid):
        return self.all_transactions().filter(
            lms_user_id=lms_user_id,
            content_uuid=content_uuid,
        )


#
# Two edx-rbac supporting models follows.
#
class EnterpriseSubsidyFeatureRole(UserRole):
    """
    User role definitions specific to Enterprise Subsidy.

     .. no_pii:
    """

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return f"EnterpriseSubsidyFeatureRole(name={self.name})"

    def __repr__(self):
        """
        Return uniquely identifying string representation.
        """
        return self.__str__()


class EnterpriseSubsidyRoleAssignment(UserRoleAssignment):
    """
    Model to map users to an EnterpriseSubsidyFeatureRole.

     .. no_pii:
    """

    role_class = EnterpriseSubsidyFeatureRole
    enterprise_id = models.UUIDField(blank=True, null=True, verbose_name='Enterprise Customer UUID')

    def get_context(self):
        """
        Generate an access context string for this assignment.

        Returns:
            str: The enterprise customer UUID or `*` if the user has access to all resources.
        """
        if self.enterprise_id:
            # converting the UUID('ee5e6b3a-069a-4947-bb8d-d2dbc323396c') to 'ee5e6b3a-069a-4947-bb8d-d2dbc323396c'
            return str(self.enterprise_id)
        return ALL_ACCESS_CONTEXT

    @classmethod
    def user_assignments_for_role_name(cls, user, role_name):
        """
        Find assignments for a given user and role name.
        """
        return cls.objects.filter(user__id=user.id, role__name=role_name)

    def __str__(self):
        """
        Human-readable string representation.
        """
        # pylint: disable=no-member
        return f"EnterpriseSubsidyRoleAssignment(name={self.role.name}, user={self.user.id})"

    def __repr__(self):
        """
        Human-readable string representation.
        """
        return self.__str__()
