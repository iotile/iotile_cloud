import os
import json

from django.contrib.auth import get_user_model
from django.utils import timezone

from iotile_cloud.utils.gid import IOTileStreamSlug, IOTileVariableSlug, IOTileProjectSlug

from apps.utils.objects.utils import get_object_by_slug
from apps.org.models import Org
from apps.org.serializers import OrgSerializer
from apps.sensorgraph.serializers import SensorGraphSerializer, VariableTemplateSerializer
from apps.sensorgraph.models import SensorGraph, VariableTemplate
from apps.sensorgraph.serializers import SensorGraphSerializer, VariableTemplateSerializer
from apps.devicetemplate.models import DeviceTemplate
from apps.devicetemplate.serializers import DeviceTemplateSerializer
from apps.projecttemplate.models import ProjectTemplate
from apps.projecttemplate.serializers import ProjectTemplateSerializer
from apps.project.models import Project
from apps.project.serializers import ProjectSerializer
from apps.physicaldevice.models import Device
from apps.physicaldevice.serializers import DeviceSerializer
from apps.physicaldevice.claim_utils import device_claim
from apps.streamevent.models import StreamEventData
from apps.streamdata.models import StreamData
from apps.stream.models import StreamId, StreamVariable
from apps.property.serializers import GenericPropertyWriteOnlySerializer
from apps.property.models import GenericProperty
from apps.configattribute.models import ConfigAttributeName, ConfigAttribute
from apps.configattribute.serializers import ConfigAttributeSerializer


from .serializers import *

user_model = get_user_model()


class BaseDeviceMock(object):

    def __init__(self, fixture_filename):
        path = os.path.join(os.path.dirname(__file__), 'data', fixture_filename)

        with open(path) as infile:
            data = json.load(infile)
        if data:
            # Orgs must be created first
            if 'org' in data:
                self.process_org(data['org'])
            if 'var_type' in data:
                self.process_var_type(data['var_type'])
            if 'device_template' in data:
                self.process_device_template(data['device_template'])
            if 'project_template' in data:
                self.process_project_template(data['project_template'])
            if 'sensor_graph' in data:
                self.process_sensor_graph(data['sensor_graph'])
            if 'project' in data:
                self.process_project(data['project'])

            self.post_process()

    def tearDown(self):
        Org.objects.all().delete()
        StreamId.objects.all().delete()
        StreamVariable.objects.all().delete()
        Device.objects.all().delete()
        Project.objects.all().delete()
        StreamData.objects.all().delete()
        StreamEventData.objects.all().delete()
        SensorGraph.objects.all().delete()
        VarType.objects.all().delete()
        VariableTemplate.objects.all().delete()
        ProjectTemplate.objects.all().delete()
        DeviceTemplate.objects.all().delete()
        ConfigAttributeName.objects.all().delete()
        ConfigAttribute.objects.all().delete()
        GenericProperty.objects.all().delete()

    def post_process(self):
        pass

    def process_org(self, orgs):
        for data in orgs:
            user = user_model.objects.get(slug=data['created_by'])
            serializer = OrgSerializer(data=data)
            assert serializer.is_valid()
            org = serializer.save(created_by=user)
            if 'vendor' in data and data['vendor']:
                org.is_vendor = True
                org.save()
            if 'config' in data and data['config']:
                # Need to process Config Attibutes
                for item in data['config']:
                    ConfigAttributeName.objects.get_or_create(
                        name=item['name'], defaults={
                            'created_by': user
                        }
                    )
                    item['target'] = org.obj_target_slug
                    config_serializer = ConfigAttributeSerializer(data=item)
                    assert config_serializer.is_valid()
                    config_serializer.save(updated_by=user, target=org)

    def process_device_template(self, templates):
        for data in templates:
            user = user_model.objects.get(slug=data['created_by'])
            serializer = DeviceTemplateSerializer(data=data)
            assert serializer.is_valid()
            serializer.save(created_by=user)

    def process_project_template(self, templates):
        for data in templates:
            user = user_model.objects.get(slug=data['created_by'])
            serializer = ProjectTemplateSerializer(data=data)
            assert serializer.is_valid()
            serializer.save(created_by=user)

    def process_var_type(self, var_types):
        for data in var_types:
            user = user_model.objects.get(slug=data['created_by'])
            serializer = VarTypeSerializer(data=data)
            assert serializer.is_valid()
            serializer.save(created_by=user)

    def process_sensor_graph(self, sensor_graphs):
        for data in sensor_graphs:
            user = user_model.objects.get(slug=data['created_by'])
            serializer = SensorGraphSerializer(data=data)
            assert serializer.is_valid()
            sg = serializer.save(created_by=user)
            if 'variable_templates' in data:
                for vt_data in data['variable_templates']:
                    if 'sg' not in vt_data:
                        vt_data['sg'] = sg.slug
                    vt_serializer = VariableTemplateSerializer(data=vt_data)
                    if not vt_serializer.is_valid():
                        print(vt_serializer.errors)
                    else:
                        vt = vt_serializer.save(created_by=user)

    def process_project(self, projects):
        for data in projects:
            user = user_model.objects.get(slug=data['created_by'])
            serializer = ProjectSerializer(data=data)
            assert serializer.is_valid()
            project = serializer.save(created_by=user)
            if 'device' in data:
                self.process_device(data['device'], project)

    def _cleanup_stream_data(self, item):
        """
        To allow us to just copy and paste from the API payload,
        need to remove item fields not needed

        :param item: a data or event object
        :return: Nothing (change by reference)
        """
        for field in ['id', 'stream', 'project', 'device', ]:
            if field in item:
                del item[field]

    def process_device(self, devices, project=None):
        for data in devices:
            user = user_model.objects.get(slug=data['created_by'])
            serializer = DeviceSerializer(data=data)
            if not serializer.is_valid():
                print(serializer.errors)
                assert True
            device = serializer.save(created_by=user)
            assert device.template
            if project:
                device_claim(device=device, project=project, claimed_by=device.created_by)

                if 'event' in data:
                    for item in data['event']:
                        project_slug = IOTileProjectSlug(project.slug)
                        varid = item.pop('variable')
                        variable_slug = IOTileVariableSlug(varid, project=project_slug)
                        stream_slug = IOTileStreamSlug()
                        stream_slug.from_parts(project=project_slug, device=device.slug, variable=variable_slug)
                        self._cleanup_stream_data(item)
                        event = StreamEventData(stream_slug=str(stream_slug), **item)
                        event.deduce_slugs_from_stream_id()
                        event.save()

                if 'data' in data:
                    for item in data['data']:
                        project_slug = IOTileProjectSlug(project.slug)
                        varid = item.pop('variable')
                        variable_slug = IOTileVariableSlug(varid, project=project_slug)
                        stream_slug = IOTileStreamSlug()
                        stream_slug.from_parts(project=project_slug, device=device.slug, variable=variable_slug)
                        self._cleanup_stream_data(item)
                        point = StreamData(stream_slug=str(stream_slug), **item)
                        point.deduce_slugs_from_stream_id()
                        point.save()

                if 'properties' in data:
                    for item in data['properties']:
                        item['target'] = device.slug
                        serializer = GenericPropertyWriteOnlySerializer(data=item)
                        if serializer.is_valid():
                            p = serializer.save(created_by=user)
                        else:
                            print(serializer.errors)
