"""
Test for utilities module.
"""
from django.test import TestCase

from enterprise_subsidy import __version__ as code_version

from ..utils import versioned_cache_key


class TestUtils(TestCase):
    """
    Tests for the utilities module.
    """
    def test_versioned_cache_key(self):
        with self.settings(CACHE_KEY_VERSION_STAMP='flapjacks'):
            self.assertEqual(
                versioned_cache_key('foo', 'bar'),
                f'foo:bar:{code_version}:flapjacks',
            )
