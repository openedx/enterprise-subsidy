"""
Utility functions used in the implementation of subsidy Transactions.
"""


def generate_transaction_reversal_idempotency_key(fulfillment_uuid, enrollment_unenrolled_at):
    """
    Generates a unique idempotency key for a transaction reversal using the fulfillment uuid and time at which the
    unenrollment occurred.
    """
    return f'unenrollment-reversal-{fulfillment_uuid}-{enrollment_unenrolled_at}'
