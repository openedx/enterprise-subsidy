0007 handling learner initiated unenrollments
#############################################

Status
******

**Accepted** May 2023

Context
*******

The enterprise-subsidy service needs to maintain records of transaction reversals for any associated platform
fulfillment cancellation. These reversals represent credit, up to the amount allocated by the original transaction,
returned to the learner's customer's ledger. As there are many sources of a learner initiated unenrollments/
cancellations, the enterprise subsidy service must take on the responsibility of monitoring the state of enterprise
fulfillments. This is necessary to ensure that any learner initiated unenrollment or cancellation of an enterprise
fulfillment object will be evaluated and that corresponding reversals are written if/when applicable.

Decision
********

In a pre-event bus driven architectural world, the enterprise subsidy service will monitor the state of recently
unenrolled enterprise fulfillment objects. It will do so by running a management command which will hit the platform
enterprise fulfillment `API <https://github.com/openedx/edx-enterprise/blob/master/enterprise/api/v1/views.py#L576>`_
somewhere between once and twice a day. The view will return a list of enterprise fulfillment objects which have been
unenrolled after the provided datetime query param filter. Notably, the subsidy service will provide an
unenrolled_after window that is larger than the frequency at which the management command runs. Meaning that if the
unenrolled_after param is set to 24 hours, the job will run >1 time within a 24 hour period. With these records, the
enterprise subsidy service will:

- First check for the existence of a transaction reversal associated with the fulfillment object's transaction and
  idempotency key. This is to prevent multiple reversal to be written for the same cancellation action. A learner
  initiated unenrollment reversal's idempotency key will be formatted as
  `unenrollment-reversal-<enterprise_fulfillment_id>-<enterprise_enrollment_unenrolled_at>`.

- Secondly, it will then evaluate whether or not the object should be refunded. Note that the refundability of an
  object is not detailed within this ADR and is ultimately up to the provider of the content and the entitlement policy
  of the course. However if the item is refundable, the subsidy service will then write a reversal record for the
  transaction.

Consequences
************

Event bus driven architecture vs routine jobs and active monitoring
+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

This management command oriented approach is not ideal as it is not event bus driven. However, the evaluation work done
on the part of the subsidy service can easily be bootstrapped by future event bus driven implementations. The hope is
that future iterations on the enterprise subsidy service will be able to hook up an event receiver to the same methods
run by the management command, but instead of manually fetching and evaluating recently unenrolled records, it would
evaluate objects which have triggered an enterprise fulfillment unenrollment/cancellation event.

Introducing the subsidy service to Jenkins
++++++++++++++++++++++++++++++++++++++++++

As it currently stands (June 2021), the enterprise subsidy service is not a part of the Jenkins CI pipeline. The
accepted implementation of running routine jobs for our services hosted on kubernetes is to utilize argoCD. within
our internal configurations we can ensure that the job is run on a schedule of our choosing.

Admin initiated unenrollment DAG and introducing a transaction reversal writing task
++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

The subsidy service currently utilizes specific django-signal driven architecture to handle admin initiated
unenrollments. This is done by listening for reversal object creations and then making a call to platform to unenroll
all associated fulfillment objects. This runs in opposition to the planned management command which will write
reversals based on the cancellation of fulfillment objects. In order to mitigate any cyclical behaviors between the two
systems, we will need to implement two stop-gaps.

- The platform enterprise fulfillment cancellation endpoint needs to verify if the fulfillment object is already
  revoked and ensure that the unenrolled_at time of the course enrollment object is not bumped if so.

- The subsidy service must check if a recently unenrolled fulfillment object already has an associated reversal object.

How the systems will interact with one another
++++++++++++++++++++++++++++++++++++++++++++++

Records updated and monitored are limited to the subsidy and edx platform services. Notably, platform course enrollment
and enterprise fulfillment objects are both housed within edx platform but are split between the enterprise package and
the LMS. The subsidy service will be responsible for maintaining reversals, as well as their transaction counterparts.

The flow for learner initiated unenrollments will be as follows:

1. Learners unenroll from a course. Notably this has multiple origin sources as it can be done from the LMS or from
   the enterprise learner/admin dashboards, however the end result is that the student.CourseEnrollment object on
   platform is de-activated.
2. Enterprise enrollment and fulfillment objects will be synchronously updated to reflect the unenrollment of the
   course enrollment via a Django signal event/handler.
3. The subsidy service will routinely hit the enterprise fulfillment recent unenrollment endpoint which will surface
   enterprise fulfillments tied to recently canceled enterprise enrollments.
4. The subsidy service will then check for the existence of a reversal object associated with the fulfillment object's
   transactions. It will then determine if transaction is refundable and if so, write a reversal object.
5. After the generation of a transaction reversal, the subsidy service sends a request to platform to unenroll
   fulfillment objects which will result in a NOOP as the fulfillments will have already been cancelled.


Rejected Alternatives
*********************

- Instead of running a routine management command, we could rely on event driven architecture to handle the monitoring
  of fulfillment objects. This would be an ideal implementation, however as the subsidy service is not yet currently
  hooked up to the event bus, and as there is no prior work done to publish any enterprise related events to the platform
  event bus, this would require more work to implement than we're willing to invest at the time of this writing.
