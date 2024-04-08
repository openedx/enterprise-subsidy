"""
Initialization app for enterprise_subsidy.apps.transaction
"""
from django.apps import AppConfig


class TransactionsConfig(AppConfig):
    """
    App configuration for the ``transaction`` module.
    """
    name = 'enterprise_subsidy.apps.transaction'

    def ready(self):
        """
        Wait to import any non-trivial dependencies until this app is ready.
        The local imports below help avoid a Django "AppConfig ready deadlock".
        """
        # pylint: disable=import-outside-toplevel
        from openedx_ledger.signals.signals import TRANSACTION_REVERSED

        from enterprise_subsidy.apps.transaction.signals.handlers import listen_for_transaction_reversal

        TRANSACTION_REVERSED.connect(listen_for_transaction_reversal)
