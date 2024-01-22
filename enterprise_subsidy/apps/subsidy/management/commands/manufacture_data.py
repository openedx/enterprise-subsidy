"""
Management command for making things with test factories
"""

from edx_django_utils.data_generation.management.commands.manufacture_data import Command as BaseCommand

from enterprise_subsidy.apps.subsidy.tests.factories import *


class Command(BaseCommand):
    """
    Management command for generating Django records from factories with custom attributes
    Example usage:
        $ ./manage.py manufacture_data --model enterprise_subsidy.apps.subsidy.models.Subsidy --title "Test Subsidy"
    """
