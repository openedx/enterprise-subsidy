0006 Transaction API State Filtering
####################################

Status
******

**Accepted**
May 2023

Context
*******

The Transactions list endpoint is used by clients to determine which
transactions already exist that match some criteria, for example:

- To find all transactions for a given ``(user, content pair)``.
- To find all transactions pertaining to some Subsidy Access Policy.

These types of queries often need to be filtered by the state of the transaction -
for example, an access policy typically wants to consider only ``pending`` or ``committed``
transactions when considering if its set of existing transactions has a summed quantity
less than some spending limit.

Decision
********

We'll augment the V2 Admin Transaction list view to support filtering by multiple,
"OR’d" values, e.g. ``state=committed&state=failed``
should return transactions in either the committed or failed state.
This view still defaults to returning otherwise-matching transactions
in `any` state.

Consequences
************

Clients will not be able to depend on the transactions API to "do the right thing"
for them - they'll have to filter down to transaction states that are
appropriate for their use cases.
