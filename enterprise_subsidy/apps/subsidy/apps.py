"""
Initialization app for enterprise_subsidy.apps.subsidy.
"""
from django.apps import AppConfig


class SubsidyConfig(AppConfig):
    """
    The app config for the ``subsidy`` app.  Notable, connects
    the signals defined in ``signals.py``.
    """
    name = 'enterprise_subsidy.apps.subsidy'

    def ready(self):
        # implicitly connect signal handlers decorated with @receiver
        # pylint: disable=unused-import,import-outside-toplevel
        from . import signals
