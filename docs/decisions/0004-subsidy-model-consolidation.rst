0004 Subsidy Model Consolidation
################################

Status
******

**Provisional**

Context
*******

The initial prototype data model provided a Subsidy abstract model and two concrete sub-classes:

.. code-block:: python

  class Subsidy(TimeStampedModel):
      class Meta:
          abstract = True
      ...
  class LearnerCreditSubsidy(Subsidy):
      ...
  class SubscriptionSubsidy(Subsidy):
      ...

However, we faced a couple of challenges during implementation:

* The FK to a Ledger on the Subsidy abstract model could not be made into a OneToOneField because it was distributed
  across two concrete tables.
* During REST API implementation we faced challenges writing clean, readable code that could reuse common edx-rbac
  viewset tools due to the subsidies being split across multiple models.

Decision
********

Neither of the challenges were insurmountable with a sufficient amount of custom logic, but since the use case of a
Subscription-backed subsidy is still up in the air at the time of writing, we decided to punt on supporting more than
the Learner Credit use case.

The result is just a single concrete Subsidy model which will refer to Learner Credit.  Going forward, we can still
fast-follow with added Subscription support by piling into the same Subscription model with a ``type`` field and
additional branching logic.

Consequences
************

The MVP will be possibly faster to implement, with the simplified model, and will unblock initial integration efforts
sooner.  Data will probably also appreciate only having one table to query for all subsidies going forward.

That said, if/when we do implement Subscription support, we may be faced with weighing either bloating a monolithic
Subisdy model, or using single-table inheritance technique using Proxy models.
