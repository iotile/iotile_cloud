# Generated by Django 3.2.8 on 2021-11-03 23:44

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('org', '0001_initial'),
        ('physicaldevice', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Fleet',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(max_length=17)),
                ('name', models.CharField(max_length=50)),
                ('description', models.TextField(blank=True, default='')),
                ('is_network', models.BooleanField(default=False)),
                ('created_on', models.DateTimeField(auto_now_add=True, verbose_name='created_on')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Fleet',
                'verbose_name_plural': 'Fleets',
                'ordering': ['org', 'name'],
            },
        ),
        migrations.CreateModel(
            name='FleetMembership',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('always_on', models.BooleanField(default=False)),
                ('is_access_point', models.BooleanField(default=False)),
                ('created_on', models.DateTimeField(auto_now_add=True, verbose_name='created_on')),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='physicaldevice.device')),
                ('fleet', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='fleet.fleet')),
            ],
            options={
                'verbose_name': 'Fleet Membership',
                'verbose_name_plural': 'Fleet Memberships',
                'ordering': ['fleet', 'device'],
                'unique_together': {('device', 'fleet')},
            },
        ),
        migrations.AddField(
            model_name='fleet',
            name='members',
            field=models.ManyToManyField(through='fleet.FleetMembership', to='physicaldevice.Device'),
        ),
        migrations.AddField(
            model_name='fleet',
            name='org',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fleets', to='org.org'),
        ),
        migrations.AlterUniqueTogether(
            name='fleet',
            unique_together={('org', 'name')},
        ),
    ]
