# Generated by Django 3.2.8 on 2021-11-03 23:44

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('s3file', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='StreamNote',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(blank=True, choices=[('sc', 'System generated (Critical)'), ('si', 'System generated (Info)'), ('fi', 'Filter generated'), ('ui', 'User Note')], default='ui', max_length=2)),
                ('target_slug', models.CharField(default='', max_length=39, null=True)),
                ('timestamp', models.DateTimeField(blank=True, null=True)),
                ('note', models.TextField(blank=True, null=True)),
                ('created_on', models.DateTimeField(auto_now_add=True, verbose_name='created_on')),
                ('attachment', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='s3file.s3file')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Stream Note',
                'verbose_name_plural': 'Stream Notes',
                'ordering': ['target_slug', 'timestamp'],
            },
        ),
    ]
