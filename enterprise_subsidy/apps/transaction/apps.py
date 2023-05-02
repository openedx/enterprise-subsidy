"""
Initialization app for enterprise_subsidy.apps.transaction
"""
from django.apps import AppConfig
from openedx_ledger.signals.signals import TRANSACTION_REVERSED

from enterprise_subsidy.apps.transaction.signals.handlers import listen_for_transaction_reversal


class TransactionsConfig(AppConfig):
    name = 'enterprise_subsidy.apps.transaction'

    def ready(self):
        TRANSACTION_REVERSED.connect(listen_for_transaction_reversal)
