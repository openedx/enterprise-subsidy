# Generated by Django 3.2.18 on 2023-02-22 22:48

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import model_utils.fields
import simple_history.models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('openedx_ledger', '0003_field_updates_20230216_1605'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('subsidy', '0009_delete_subsidy_tables_20230221_2337'),
    ]

    operations = [
        migrations.CreateModel(
            name='Subsidy',
            fields=[
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ('title', models.CharField(blank=True, max_length=255, null=True)),
                ('starting_balance', models.BigIntegerField()),
                ('unit', models.CharField(choices=[('usd_cents', 'U.S. Dollar (Cents)'), ('seats', 'Seats in a course'), ('jpy', 'Japanese Yen')], db_index=True, default='usd_cents', max_length=255)),
                ('reference_id', models.CharField(blank=True, max_length=255, null=True)),
                ('reference_type', models.CharField(choices=[('opportunity_product_id', 'Opportunity Product ID')], db_index=True, default='opportunity_product_id', max_length=255)),
                ('enterprise_customer_uuid', models.UUIDField(db_index=True)),
                ('active_datetime', models.DateTimeField(default=None, null=True)),
                ('expiration_datetime', models.DateTimeField(default=None, null=True)),
                ('ledger', models.OneToOneField(null=True, on_delete=django.db.models.deletion.SET_NULL, to='openedx_ledger.ledger')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='HistoricalSubsidy',
            fields=[
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)),
                ('title', models.CharField(blank=True, max_length=255, null=True)),
                ('starting_balance', models.BigIntegerField()),
                ('unit', models.CharField(choices=[('usd_cents', 'U.S. Dollar (Cents)'), ('seats', 'Seats in a course'), ('jpy', 'Japanese Yen')], db_index=True, default='usd_cents', max_length=255)),
                ('reference_id', models.CharField(blank=True, max_length=255, null=True)),
                ('reference_type', models.CharField(choices=[('opportunity_product_id', 'Opportunity Product ID')], db_index=True, default='opportunity_product_id', max_length=255)),
                ('enterprise_customer_uuid', models.UUIDField(db_index=True)),
                ('active_datetime', models.DateTimeField(default=None, null=True)),
                ('expiration_datetime', models.DateTimeField(default=None, null=True)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField()),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('ledger', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='openedx_ledger.ledger')),
            ],
            options={
                'verbose_name': 'historical subsidy',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': 'history_date',
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
    ]