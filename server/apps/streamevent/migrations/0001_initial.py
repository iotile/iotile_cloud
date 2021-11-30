# Generated by Django 3.2.8 on 2021-11-03 23:44

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='StreamEventData',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stream_slug', models.CharField(default='', max_length=39, null=True)),
                ('project_slug', models.CharField(default='', max_length=12, null=True)),
                ('device_slug', models.CharField(default='', max_length=33, null=True)),
                ('variable_slug', models.CharField(default='', max_length=18, null=True)),
                ('device_timestamp', models.BigIntegerField(blank=True, null=True)),
                ('timestamp', models.DateTimeField(blank=True, null=True)),
                ('streamer_local_id', models.PositiveIntegerField(default=0)),
                ('dirty_ts', models.BooleanField(default=False)),
                ('status', models.CharField(choices=[('unk', 'unknown'), ('cln', 'clean'), ('drt', 'dirty'), ('utc', 'utc timestamp')], default='unk', max_length=3)),
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False)),
                ('s3_key_path', models.CharField(blank=True, default='', max_length=20, null=True)),
                ('ext', models.CharField(blank=True, choices=[('json', 'Json Data File'), ('json.gz', 'GZipped Json Data File'), ('csv', 'CSV Data File')], default='json', max_length=10, null=True)),
                ('extra_data', models.JSONField(blank=True, null=True)),
                ('format_version', models.IntegerField(default=2)),
            ],
            options={
                'verbose_name': 'Stream Event Entry',
                'verbose_name_plural': 'Stream Event Entries',
                'ordering': ['stream_slug', 'streamer_local_id', 'timestamp'],
            },
        ),
    ]
