# Generated by Django 3.2.8 on 2021-11-03 23:44

import django.contrib.postgres.fields
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('org', '0001_initial'),
        ('project', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('sensorgraph', '0001_initial'),
        ('devicetemplate', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Device',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('slug', models.SlugField(default='', max_length=24)),
                ('external_id', models.CharField(blank=True, default='', max_length=24)),
                ('label', models.CharField(blank=True, default='', max_length=100)),
                ('lon', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('lat', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('last_known_id', models.PositiveIntegerField(blank=True, default=1)),
                ('last_reboot_ts', models.DateTimeField(blank=True, null=True)),
                ('created_on', models.DateTimeField(auto_now_add=True, verbose_name='created_on')),
                ('claimed_on', models.DateTimeField(blank=True, null=True, verbose_name='claimed_on')),
                ('active', models.BooleanField(default=True)),
                ('state', models.CharField(blank=True, choices=[('N0', 'Normal - Inactive'), ('N1', 'Normal - Active'), ('B0', 'Busy - Resetting'), ('B1', 'Busy - Archiving')], default='N1', max_length=2, verbose_name='Device State')),
                ('claimed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='claimed_devices', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_devices', to=settings.AUTH_USER_MODEL)),
                ('org', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='devices', to='org.org')),
                ('project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='devices', to='project.project')),
                ('sg', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='devices', to='sensorgraph.sensorgraph')),
                ('template', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='devices', to='devicetemplate.devicetemplate')),
            ],
            options={
                'verbose_name': 'IOTile Device',
                'verbose_name_plural': 'IOTile Devices',
                'ordering': ['id'],
            },
        ),
        migrations.CreateModel(
            name='DeviceStatus',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('last_known_id', models.BigIntegerField(blank=True, default=1)),
                ('last_report_ts', models.DateTimeField(blank=True, null=True)),
                ('health_check_enabled', models.BooleanField(default=False)),
                ('health_check_period', models.PositiveIntegerField(default=7200)),
                ('last_known_state', models.CharField(choices=[('UNK', 'Device is in UNK state. No uploads found'), ('FAIL', 'Device is in FAIL state'), ('OK', 'Device is in OK State'), ('DSBL', 'Device status check is disabled')], default='UNK', max_length=4)),
                ('notification_recipients', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=64), blank=True, default=list, size=None)),
                ('device', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='status', to='physicaldevice.device')),
            ],
            options={
                'verbose_name': 'IOTile Device Status',
                'verbose_name_plural': 'IOTile Device Statuses',
                'ordering': ['device'],
            },
        ),
    ]
