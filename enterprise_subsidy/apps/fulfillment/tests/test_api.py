"""
Tests for functions defined in the ``api.py`` module.
"""
from unittest import mock

import pytest
from django.test import TestCase


class GEAGFulfillmentHandlerTestCase(TestCase):
    """
    Test GEAGFulfillmentHandler
    """
    def setUp(self):
        super().setUp()

    def test_nothing(self):
        assert True