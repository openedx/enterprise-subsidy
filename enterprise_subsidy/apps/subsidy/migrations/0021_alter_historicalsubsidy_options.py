# Generated by Django 4.2.5 on 2023-11-06 20:06

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('subsidy', '0020_remove_subsidy_unique_reference_id_non_internal'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='historicalsubsidy',
            options={'get_latest_by': ('history_date', 'history_id'), 'ordering': ('-history_date', '-history_id'), 'verbose_name': 'historical subsidy', 'verbose_name_plural': 'historical subsidys'},
        ),
    ]
