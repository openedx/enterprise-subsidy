"""
Core utility function.
"""
from datetime import datetime

from django.conf import settings
from pytz import UTC

from enterprise_subsidy import __version__ as code_version

CACHE_KEY_SEP = ':'


def versioned_cache_key(*args):
    """
    Utility to produce a versioned cache key, which includes
    an optional settings variable and the current code version,
    so that we can perform key-based cache invalidation.
    """
    components = [str(arg) for arg in args]
    components.append(code_version)
    if stamp_from_settings := getattr(settings, 'CACHE_KEY_VERSION_STAMP', None):
        components.append(stamp_from_settings)
    return CACHE_KEY_SEP.join(components)


def localized_utcnow():
    """Helper function to return localized utcnow()."""
    return UTC.localize(datetime.utcnow())  # pylint: disable=no-value-for-parameter
