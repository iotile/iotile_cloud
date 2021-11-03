# Generated by Django 3.2.8 on 2021-11-03 23:44

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('org', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Invitation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email', models.EmailField(max_length=254, verbose_name='email address')),
                ('accepted', models.BooleanField(default=False, verbose_name='accepted')),
                ('sent_on', models.DateTimeField(null=True, verbose_name='sent on')),
                ('role', models.CharField(default='m1', max_length=3, verbose_name='Permissions Role to set new user to')),
                ('created_on', models.DateTimeField(auto_now_add=True, verbose_name='created_on')),
                ('org', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invitations', to='org.org', verbose_name='Company Name')),
                ('sent_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invitations', to=settings.AUTH_USER_MODEL, verbose_name='sent by')),
            ],
            options={
                'ordering': ['org', 'email'],
                'unique_together': {('org', 'email')},
            },
        ),
    ]