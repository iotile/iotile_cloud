# Generated by Django 3.2.8 on 2021-11-03 23:44

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DeviceKey',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(max_length=24)),
                ('type', models.CharField(choices=[('USR', 'User Key'), ('SSH', 'SSH Key'), ('X-API-KEY', 'API Gateway Key'), ('A-JWT-KEY', 'Secret Key for a-jwt generation'), ('MQTT', 'MQTT Password for device topics')], default='USR', max_length=16)),
                ('secret', models.TextField()),
                ('downloadable', models.BooleanField(blank=True, default=False)),
                ('created_on', models.DateTimeField(auto_now_add=True, verbose_name='created_on')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Device Key',
                'verbose_name_plural': 'Device Keys',
                'ordering': ['slug', 'type'],
                'unique_together': {('slug', 'type')},
            },
        ),
    ]
