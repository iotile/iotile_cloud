import json
import os

from apps.configattribute.models import ConfigAttribute
from apps.projecttemplate.models import ProjectTemplate
from apps.stream.models import StreamVariable
from apps.streamfilter.models import *
from apps.utils.iotile.variable import SYSTEM_VID
from apps.verticals.helpers.device_claim_helper import DeviceVerticalClaimHelper


class ShippingDeviceVerticalClaimHelper(DeviceVerticalClaimHelper):

    def adjust_device(self):
        """
        All shipping devices should be set to inactive while claiming
        """
        self._device.state = 'N0'
        self._device.label = '{} [{}]'.format(self._device.template.name, self._device.slug)
        self._device.set_active_from_state()

    def setup_project(self, project):
        """
        Setup project for a shipping app:

        1. Set proper project template
        2. Create Trip Summary Filter if needed
        3. Create Trip Update Filter if needed
        4. Create Mid-Trip Update Filter if needed

        :param project: Project to setup
        """

        # 1.- Make sure the project template is set to the shipping one
        project_template = ProjectTemplate.objects.filter(name='Shipping Template').last()
        project.project_template = project_template
        project.save()

        org = project.org

        # 2. Create required filters
        var = {}
        for name, vid in [
                ('End of Trip', 'TRIP_END'),
                ('Trip Update', 'TRIP_UPDATE'),
                ('Mid-Trip Data Upload', 'MID_TRIP_DATA_UPLOAD')
            ]:
            try:
                var[vid] = StreamVariable.objects.get(
                    project=project,
                    org=org,
                    lid=int(SYSTEM_VID[vid], 16),
                )
            except StreamVariable.DoesNotExist:
                var[vid] = StreamVariable.objects.create_variable(
                    name=name,
                    project=project,
                    org=org,
                    created_by=org.created_by,
                    lid=int(SYSTEM_VID[vid], 16),
                )

        # Email settings
        extra_payload = {
            'generator': 'end_of_trip',
            'notification_recipients': ['org:admin']
        }

        # Create Trip Summary Filter if needed
        try:
            f1 = StreamFilter.objects.get(
                project=project, variable=var['TRIP_END'], device__isnull=True
            )
            logger.info('Reusing f1 filter for project: {}'.format(f1))
        except StreamFilter.DoesNotExist:
            f1 = StreamFilter.objects.create_filter_from_project_and_variable(
                name='End of Trip', proj=project, var=var['TRIP_END'], created_by=org.created_by
            )
            state1 = State.objects.create(label="END", filter=f1, created_by=org.created_by)
            StreamFilterAction.objects.create(
                type='smry', created_by=org.created_by, extra_payload=extra_payload, on='entry', state=state1
            )
            transition1 = StateTransition.objects.create(src=state1, dst=state1, filter=f1, created_by=org.created_by)
            StreamFilterTrigger.objects.create(
                operator='bu', created_by=org.created_by, filter=f1, transition=transition1
            )

        # Create Trip Update Filter if needed
        extra_payload['generator'] = 'trip_update'
        try:
            f2 = StreamFilter.objects.get(
                project=project, variable=var['TRIP_UPDATE'], device__isnull=True
            )
            logger.info('Reusing f2 filter for project: {}'.format(f2))
        except StreamFilter.DoesNotExist:
            f2 = StreamFilter.objects.create_filter_from_project_and_variable(
                name='Trip Update', proj=project, var=var['TRIP_UPDATE'], created_by=org.created_by
            )
            state2 = State.objects.create(label="UPDATE", filter=f2, created_by=org.created_by)
            StreamFilterAction.objects.create(
                type='smry', created_by=org.created_by, extra_payload=extra_payload, on='entry', state=state2
            )
            transition2 = StateTransition.objects.create(src=state2, dst=state2, filter=f2, created_by=org.created_by)
            StreamFilterTrigger.objects.create(
                operator='bu', created_by=org.created_by, filter=f2, transition=transition2
            )

        # Create Mid-Trip Update Filter if needed
        extra_payload['generator'] = 'end_of_trip'
        try:
            f3 = StreamFilter.objects.get(
                project=project, variable=var['MID_TRIP_DATA_UPLOAD'], device__isnull=True
            )
            logger.info('Reusing f3 filter for project: {}'.format(f3))
        except StreamFilter.DoesNotExist:
            f3 = StreamFilter.objects.create_filter_from_project_and_variable(
                name='Mid-Trip Data Upload', proj=project, var=var['MID_TRIP_DATA_UPLOAD'], created_by=org.created_by
            )
            state3 = State.objects.create(label="DATA_UPDATE", filter=f3, created_by=org.created_by)
            StreamFilterAction.objects.create(
                type='smry', created_by=org.created_by, extra_payload=extra_payload, on='entry', state=state3
            )
            transition3 = StateTransition.objects.create(src=state3, dst=state3, filter=f3, created_by=org.created_by)
            StreamFilterTrigger.objects.create(
                operator='bu', created_by=org.created_by, filter=f3, transition=transition3
            )

    def setup_org(self, org):
        """
        Setup org for a shipping app:

        All Shipping Organizations need to have a set of config attributes
        for the UI and Analytics to work.
        These attributes are defined on the data/default-config.json file

        :param org: Org to setup
        """

        dirname = os.path.dirname(__file__)
        filename = os.path.join(dirname, 'data', 'default-config.json')
        logger.info('Loading Shipping Org Config from: {}'.format(filename))

        # Create new Attribute for this Organization
        with open(filename) as infile:
            data = json.load(infile)
            for item in data['attributes']:
                ConfigAttribute.objects.get_or_create_attribute(
                    target=org,
                    name=item['name'],
                    data=item['data'],
                    updated_by=org.created_by
                )
