# Generated by Django 3.2.8 on 2021-11-03 23:44

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('s3file', '0001_initial'),
        ('vartype', '0001_initial'),
        ('org', '0001_initial'),
        ('projecttemplate', '0001_initial'),
        ('property', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='GenericPropertyTemplate',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=40)),
            ],
            options={
                'verbose_name': 'Property Template',
                'verbose_name_plural': 'Property Templates',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='SensorGraph',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50)),
                ('major_version', models.IntegerField(default=0, verbose_name='Major')),
                ('minor_version', models.IntegerField(default=0, verbose_name='Minor')),
                ('patch_version', models.IntegerField(default=0, verbose_name='Patch')),
                ('slug', models.SlugField(max_length=60, unique=True)),
                ('created_on', models.DateTimeField(auto_now_add=True, verbose_name='created_on')),
                ('active', models.BooleanField(default=True)),
                ('report_processing_engine_ver', models.PositiveIntegerField(default=0)),
                ('app_tag', models.PositiveIntegerField(default=0, verbose_name='App Tag')),
                ('app_major_version', models.PositiveIntegerField(default=0, verbose_name='App Tag Major Ver')),
                ('app_minor_version', models.PositiveIntegerField(default=0, verbose_name='App Tag Minor Ver')),
                ('ui_extra', models.JSONField(blank=True, null=True)),
                ('description', models.TextField(blank=True, verbose_name='Short Description')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('org', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='sensor_graphs', to='org.org')),
                ('org_properties', models.ManyToManyField(blank=True, to='property.GenericPropertyOrgTemplate')),
                ('project_template', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sensor_graphs', to='projecttemplate.projecttemplate')),
                ('sgf', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='s3file.s3file')),
            ],
            options={
                'verbose_name': 'Sensor Graph',
                'verbose_name_plural': 'Sensor Graphs',
                'ordering': ['name', 'major_version', 'minor_version', 'patch_version'],
                'unique_together': {('name', 'major_version', 'minor_version', 'patch_version')},
            },
        ),
        migrations.CreateModel(
            name='VariableTemplate',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(blank=True, default='', max_length=60, verbose_name='Label')),
                ('lid_hex', models.CharField(default='', max_length=4, verbose_name='Local Variable ID')),
                ('derived_lid_hex', models.CharField(blank=True, default='', max_length=4, verbose_name='Derived Local Variable ID')),
                ('m', models.IntegerField(default=1)),
                ('d', models.IntegerField(default=1)),
                ('o', models.FloatField(default=0.0)),
                ('ctype', models.CharField(default='unsigned int', max_length=16)),
                ('app_only', models.BooleanField(default=False)),
                ('web_only', models.BooleanField(default=False)),
                ('created_on', models.DateTimeField(auto_now_add=True, verbose_name='created_on')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('default_input_unit', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='vartype.vartypeinputunit')),
                ('default_output_unit', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='vartype.vartypeoutputunit')),
                ('sg', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='variable_templates', to='sensorgraph.sensorgraph')),
                ('var_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='variable_templates', to='vartype.vartype')),
            ],
            options={
                'verbose_name': 'Variable Template',
                'verbose_name_plural': 'Variable Templates',
                'ordering': ['sg', 'lid_hex'],
            },
        ),
        migrations.CreateModel(
            name='DisplayWidgetTemplate',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(blank=True, default='', max_length=60, verbose_name='Label')),
                ('lid_hex', models.CharField(default='', max_length=4, verbose_name='Local Variable ID')),
                ('derived_unit_type', models.CharField(blank=True, default='', max_length=20)),
                ('show_in_app', models.BooleanField(default=False)),
                ('show_in_web', models.BooleanField(default=False)),
                ('type', models.CharField(choices=[('val', 'Data Stream Value'), ('btn', 'Default Button'), ('sbt', 'Switch Button')], default='val', max_length=4)),
                ('args', models.JSONField(blank=True, null=True)),
                ('created_on', models.DateTimeField(auto_now_add=True, verbose_name='created_on')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('sg', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='display_widget_templates', to='sensorgraph.sensorgraph')),
                ('var_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='display_widget_templates', to='vartype.vartype')),
            ],
            options={
                'verbose_name': 'Display Widget',
                'verbose_name_plural': 'Display Widgets',
                'ordering': ['sg', 'lid_hex'],
            },
        ),
    ]
