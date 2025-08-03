0008 Idempotency Keys
#####################

Status
******

**Accepted** May 2023

Context
*******

Sometimes, it might make sense to perform the exact same API operation twice,
sometimes not.  If the DB allows duplicate resources, and two identical
requests are made to create two identical resources, who's to say the second request was
a mistake?  One might use the request time as a heuristic to guess whether it
was a mistake, but that falls prey to edge cases.

Transaction records link together [ledger, learner, content], are immutable
once created, and can be reversed by creating and linking a Reversal record.
When the client requests to create a new Transaction with the exact same combo
of [ledger, learner, content] as an existing one, the service needs to gather
additional context to distinguish between two possible scenarios:

1. The second request was simply a re-try of an earlier request, whose response
   was interrupted by a temporarily degraded network, but nevertheless resulted
   in a successful creation.  The original intention was to create only one
   transaction, so the service SHOULD NOT create a new transaction (just return
   the first).
2. The second request is an effort to create a second identical transaction, so
   the service SHOULD create a new transaction.

Idempotency keys help to signal the original intention of the client to the
system handling the request.  If the requester first constructed a unique
idempotency key, then passed that same key to every request in the retry loop,
the service will have all the information it needs to distinguish between
scenario 1 (colliding idempotency keys) and scenario 2 (differing idempotency
keys).

Idempotency keys are not meant to replace database level uniqueness
constraints, the latter of which being appropriate when resources have clear and
obvious uniqueness requirements that are easy to prove will apply to every case
in the past, present and future.  However, it may not always be possible to
construct a uniqueness constraint that is so complex that it adequately
encapsulates all edge cases of the desired business logic.

Decision
********

For all REST/python APIs to create Subsidy/Ledger, Transaction, and Reversal
objects, incorporate idempotency keys to de-duplicate requests from the client.
This should be implemented via an ``idempotency_key`` request body parameter.
It should be stored as a like-named database field on all target objects, and
there should be a unique constraint on that new db column.

The client should generate idempotency keys for each object type as follows:

+--------------------+------------------+--------------------------------------------------------------------+---------------------------------+
| Client             | Object to create | Idempotency key format                                             | Notes                           |
+====================+==================+====================================================================+=================================+
| enterprise-subsidy | Ledger           | ``ledger-for-subsidy-{subsidy_uuid}``                              |                                 |
+--------------------+------------------+--------------------------------------------------------------------+---------------------------------+
| enterprise-subsidy |                  | ``ledger-for-subsidy-{subsidy_uuid}-{quantity}-initial-deposit``   | First ledger credit only        |
+--------------------+ Transaction      +--------------------------------------------------------------------+---------------------------------+
| enterprise-access  |                  | ``ledger-for-subsidy-{subsidy_uuid}-{hashed transaction data}`` Δ  | All subsequent ledger debits    |
+--------------------+------------------+--------------------------------------------------------------------+---------------------------------+
|                    |                  | ``admin-invoked-reverse-{transaction_uuid}``                       | Reversals initiated by admins   |
| enterprise-subsidy | Reversal         +--------------------------------------------------------------------+---------------------------------+
|                    |                  | ``unenrollment-reversal-{fulfillment_identifier}-{unenrolled_at}`` | Reversals initiated by learners |
+--------------------+------------------+--------------------------------------------------------------------+---------------------------------+

Δ = The hashed transaction metadata should incorporate the following inputs:

* lms_user_id to enroll into a course.
* content_key to enroll the learner into.
* subsidy_access_policy_uuid pertaining to the policy which "granted" this redemption.
* A list of all historical inactive redemptions for the learner and course.

This approach differs from Stripe's idempotency keys in a ways:

* Stripe's idempotency keys "expire" after 24 hours.  Our approach will
  not expire idempotency keys because we will be leveraging idempotency keys
  slightly more for data integrity.
* Stripe's idempotency keys are passed via HTTP headers, emphasizing that they
  are considered request metadata, as opposed to resource data.  This makes it
  easier to justify making idempotency keys ephemeral.
* Stripe's idempotency keys double as cache keys depending on the response
  code.  Our approach, on the other hand, will make no attempt to cache
  responses based on idempotency key, which may be functionally more correct
  but has slower performance.

Stripe's idempotency keys have a smaller scope: to ONLY prevent duplicate
requests caused by networking issues, but not to also enforce long-term data
integrity.  We may decide in the future to draw inspiration from Stripe's
approach by combining idempotency keys with more server-side integrity
constraints.

Consequences
************

Scope covers data integrity
+++++++++++++++++++++++++++

Our approach as described above covers using idempotency keys for both
de-duplicating requests and enforcing data integrity.  This means it is still
possible for a malicious actor, buggy client, or confused engineer to construct
a request that does produce an idempotency key which adequately prevents
duplicate objects from being created.  For instance, you could mock a client
and use ``curl`` to directly create a duplicate transaction simply by passing a
randomized value for the ``idempotency_key``.

Rejected Alternatives
*********************

It may have been possible to construct relatively complex uniqueness checking
logic which adequately simulates the original intention of a create transaction
request.  E.g. we could add a save hook to validate that at most one
transaction may exist with a particular [ledger, learner, content] and
reversal.uuid == null and reversal.state != failed.  This approach would cover
the specific scenario described above, but may need to be expanded to cover
others.  It could be a viable and robust approach since both client and server
are authored by the same developer, so unlike with Stripe, we can bake all or
most possible client intentions into the backend.

In the end, we did not explore this approach before completing the MVP, so it
was de facto rejected.
