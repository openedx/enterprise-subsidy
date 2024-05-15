"""
Functions for serializing and emiting Open edX event bus signals.
"""
from openedx_events.enterprise.data import LedgerTransaction, LedgerTransactionReversal
from openedx_events.enterprise.signals import (
    LEDGER_TRANSACTION_COMMITTED,
    LEDGER_TRANSACTION_CREATED,
    LEDGER_TRANSACTION_FAILED,
    LEDGER_TRANSACTION_REVERSED
)


def serialize_transaction(transaction_record):
    """
    Serializes the ``transaction_record``into a defined set of attributes
    for use in the event-bus signal.
    """
    reversal_data = None
    if reversal_record := transaction_record.get_reversal():
        reversal_data = LedgerTransactionReversal(
            uuid=reversal_record.uuid,
            created=reversal_record.created,
            modified=reversal_record.modified,
            idempotency_key=reversal_record.idempotency_key,
            quantity=reversal_record.quantity,
            state=reversal_record.state,
        )
    data = LedgerTransaction(
        uuid=transaction_record.uuid,
        created=transaction_record.created,
        modified=transaction_record.modified,
        idempotency_key=transaction_record.idempotency_key,
        quantity=transaction_record.quantity,
        state=transaction_record.state,
        ledger_uuid=transaction_record.ledger.uuid,
        subsidy_access_policy_uuid=transaction_record.subsidy_access_policy_uuid,
        lms_user_id=transaction_record.lms_user_id,
        content_key=transaction_record.content_key,
        parent_content_key=transaction_record.parent_content_key,
        fulfillment_identifier=transaction_record.fulfillment_identifier,
        reversal=reversal_data,
    )
    return data


def send_transaction_created_event(transaction_record):
    """
    Sends the LEDGER_TRANSACTION_CREATED open edx event for the given ``transaction_record``.

    Parameters:
      transaction_record (openedx_ledger.models.Transaction): A transaction record.
    """
    LEDGER_TRANSACTION_CREATED.send_event(
        ledger_transaction=serialize_transaction(transaction_record),
    )


def send_transaction_committed_event(transaction_record):
    """
    Sends the LEDGER_TRANSACTION_COMMITTED open edx event for the given ``transaction_record``.

    Parameters:
      transaction_record (openedx_ledger.models.Transaction): A transaction record.
    """
    LEDGER_TRANSACTION_COMMITTED.send_event(
        ledger_transaction=serialize_transaction(transaction_record),
    )


def send_transaction_failed_event(transaction_record):
    """
    Sends the LEDGER_TRANSACTION_FAILED open edx event for the given ``transaction_record``.

    Parameters:
      transaction_record (openedx_ledger.models.Transaction): A transaction record.
    """
    LEDGER_TRANSACTION_FAILED.send_event(
        ledger_transaction=serialize_transaction(transaction_record),
    )


def send_transaction_reversed_event(transaction_record):
    """
    Sends the LEDGER_TRANSACTION_REVERSED open edx event for the given ``transaction_record``.

    Parameters:
      transaction_record (openedx_ledger.models.Transaction): A transaction record.
    """
    LEDGER_TRANSACTION_REVERSED.send_event(
        ledger_transaction=serialize_transaction(transaction_record),
    )
