# Generated by Django 3.2.8 on 2021-11-03 23:44

import uuid

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
            name='S3File',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(blank=True, max_length=100, null=True)),
                ('bucket', models.CharField(max_length=50)),
                ('key', models.CharField(max_length=160, unique=True)),
                ('created_on', models.DateTimeField(auto_now_add=True, verbose_name='created_on')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='s3files', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'S3 File',
                'verbose_name_plural': 'S3 Files',
                'ordering': ['bucket', 'key'],
            },
        ),
    ]
