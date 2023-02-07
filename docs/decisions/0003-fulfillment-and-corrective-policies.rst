0003 Transaction fulfillment and corrective policies
####################################################

Status
******

**Accepted**

Context
*******
To *fulfill* a subsidy transaction, we'll create either an Enterprise ``CourseEntitlement``,
``CourseEnrollment``, or both within edx-enterprise (really edx-platform). This document defines
corrective policies for known possible failure modes at the interface between subsidy transactions and
the edx-enterprise Enrollment/Entitlement layer.

A successful fulfillment roundtrip between enterprise-subsidy and edx-enterprise involves:

- During the request from enterprise-subsidy to edx-enterprise, a transaction identifier being written
  in edx-enterprise and associated with the ``CourseEntitlement`` and/or the ``CourseEnrollment``
  that was created to fulfill the transaction.
- When edx-enterprise responds to this request, it should result in an identifier associated with the entitlement
  or enrollment being written as a ``reference identifier`` on the subsidy transaction record, thus
  "committing" the transaction (not to be confused with a relational database commit).
  
Consider the following cases:

- What happens when the Subsidy API requests an entitlement/enrollment creation during fulfillment,
  and then becomes unreachable before it can process a successful response from the Enrollment API? We end up with
  *an un-committed ledger transaction* in enterprise-subsidy, but valid/complete entitlement or enrollment records
  that reference the transaction id within edx-enterprise.
- What happens when we create a ledger transaction in enterprise-subsidy, but there’s no reference identifier
  (i.e. no related enrollment records) to indicate that the fulfillment is complete and the transaction can be committed?
  This might happen if the edx-enterprise enrollment API never responds (successfully) to the enterprise-subsidy request.

Another way to look at this, from the Subsidy API's perspective: if there's no ``reference identifier`` on a transaction
record, the Subsidy API doesn't know if an entitlement/enrollment *does not exist* to fulfill the transaction, or
if the entitlement/enrollment fulfilling the transaction *does exist*, but the Subsidy API didn't receive the
identifier of it to store as its ``reference identifier``.

Our corrective policy for transaction fulfillment should deal with both these cases.
An important assumption we make in our decisions is that the act of creating enterprise Entitlement and Enrollment
records is idempotent.  We further assume that the act of creating enterprise-subsidy transactions is idempotent.

Decision
********

In summary: Subsidy Fulfillment actions should optimistically retry on failure, keying off the *transaction* record state.
"Failure" means a state where a created but not yet committed ledger ``transaction`` records exists
(i.e. there is no ``reference identifier`` value on the transaction).

The exact implementation of "optimistic retries" is somewhat up for debate - we could imagine the fulfillment action
as an asynchronous celery task that retries indefinitely (or up to some fairly high maximum).  The fulfillment action
might block on the first attempt of the task, and retry asynchronously on failure.

Alternatively, we might imagine retries as a combination of the hypothetical retrying-task above,
*and* an asynchronous event-consumer that subscribes to events related to the creation
of enterprise course entitlements/enrollments.

No gos
======
We **will not** handle a case where a non-enterprise user a course and some time later becomes an enterprise learner,
who may wish to be entitled to that course by their enterprise via a subsidy.

Alternatives Considered
***********************

Pessimistic ledger
==================
We could create a cron job or event consumer in the enterprise enrollment API that soft-deletes any entitlements/enrollments
without a corresponding enterprise-subsidy transaction record (such a job would look up a transaction record by the
reference identifier, which would be null in case of failures/request interruptions).  This would have several undesirable
consequences:

- We have soft-deleted enrollments floating around.
- There would be some period of time where the user appears enrolled, which perhaps the user would notice.

Subsidy API event consumer only
===============================
We could have only one piece of the decision above: an asynchronous event-consumer that subscribes to events
related to the creation of enterprise course entitlements/enrollments - the consumer would find the correct
transaction to update the ``reference identifier`` of, and then commit the transaction.

Doing this is not bad, but we prefer the belt **and** suspenders approach described in the decision section above.

Consequences
************
There are several consequences of this decision:

- It becomes **necessary** to incorporate a post-fulfillment attempt interstitial page to our UX flow
  *for all fulfillment attempts*, successful or otherwise (on success, this page likely redirects to a place
  with a clear call-to-action), so that we can clarify to the user if we're currently retrying fulfillment.
- It's likely useful to enumerate distinct ``CREATED``, ``PENDING``, and ``COMMITTED`` states for our ledger transaction records.
- We have to do something to model enrollment records in a way that makes it clear if a transaction reference is required,
  and if so, what the reference id is.  So make it very obvious what an “orphaned enrollment” is under our desired architecture.
