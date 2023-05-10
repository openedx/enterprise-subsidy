"""
Initialization for the ``enterprise_subsidy.apps.core`` app
"""
from django.apps import AppConfig


class CoreConfig(AppConfig):
    """
    The app config for the ``core`` app.  On ready, updates
    the ``AppConfiguration`` model with the latest commit hash.
    """
    name = 'enterprise_subsidy.apps.core'

    def ready(self):
        """
        Checks/sets the latest commit hash in the config model for our application.
        https://github.com/openedx/django-config-models/blob/master/config_models/models.py
        """
        from .api import current_commit_hash
        from .models import AppConfiguration

        latest_commit_hash = current_commit_hash()
        if not latest_commit_hash:
            # Bail if we can't read the latest hash for whatever reason.
            return

        # Read the latest config record with a commit hash that matches the latest commit hash.
        # If such a record already exists and is enabled, we're all done.
        # If such a record exists and is not enabled, we enable it.
        # If such a record does _not_ exist, current() returns a new entry
        # which is not persisted, has ``enabled`` False,
        # and has KEY_FIELDS values (like ``commit_hash``) populated from its args.
        current_configuration = AppConfiguration.current(latest_commit_hash)
        if not current_configuration.enabled:
            current_configuration.enabled = True
            current_configuration.save()
