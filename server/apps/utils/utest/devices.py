from datetime import timedelta

from django.utils import dateparse, timezone

from apps.configattribute.models import ConfigAttribute, ConfigAttributeName
from apps.devicetemplate.models import DeviceTemplate
from apps.org.models import Org
from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.projecttemplate.models import ProjectTemplate
from apps.sensorgraph.models import SensorGraph, VariableTemplate
from apps.stream.models import StreamId, StreamVariable
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData
from apps.vartype.models import VarType, VarTypeDecoder, VarTypeInputUnit, VarTypeOutputUnit

from .base import BaseDeviceMock


class TripDeviceMock(BaseDeviceMock):
    """
    Mocks data for a POD-1M like Shipping Device.
    Includes:
    - DeviceTemplate and SensorGraph
    - Org and Project
    - Device and Streams
    - Basic Data
    """

    def __init__(self):
        super(TripDeviceMock, self).__init__('trip1.json')

    def testMock(self, testObj):
        testObj.assertEqual(Org.objects.count(), 2)
        testObj.assertEqual(DeviceTemplate.objects.count(), 1)
        testObj.assertEqual(ProjectTemplate.objects.count(), 1)
        testObj.assertEqual(SensorGraph.objects.count(), 1)
        testObj.assertEqual(Project.objects.count(), 2)
        testObj.assertEqual(VariableTemplate.objects.count(), 9)
        testObj.assertEqual(VarType.objects.count(), 7)
        testObj.assertEqual(Device.objects.count(), 1)
        testObj.assertEqual(Device.objects.first().template.id, DeviceTemplate.objects.first().id)
        testObj.assertEqual(StreamVariable.objects.count(), 10)
        testObj.assertEqual(StreamId.objects.count(), 9)
        testObj.assertEqual(StreamData.objects.count(), 7)
        testObj.assertEqual(StreamEventData.objects.count(), 10)
        testObj.assertEqual(ConfigAttributeName.objects.count(), 5)
        testObj.assertEqual(ConfigAttribute.objects.count(), 5) # Created automatically



class ThreeWaterMetersDeviceMocks(BaseDeviceMock):
    """
    Three water meters
    """

    def __init__(self):
        super(ThreeWaterMetersDeviceMocks, self).__init__('water1.json')

    def testMock(self, testObj):
        testObj.assertEqual(Org.objects.count(), 2)
        testObj.assertEqual(DeviceTemplate.objects.count(), 1)
        testObj.assertEqual(ProjectTemplate.objects.count(), 1)
        testObj.assertEqual(SensorGraph.objects.count(), 1)
        testObj.assertEqual(Project.objects.count(), 3)
        testObj.assertEqual(Device.objects.count(), 3)
        testObj.assertEqual(VariableTemplate.objects.count(), 2)
        testObj.assertEqual(VarType.objects.count(), 1)
        testObj.assertEqual(StreamVariable.objects.count(), 4)
        testObj.assertEqual(StreamId.objects.count(), 6)

    def post_process(self):

        p1 = Project.objects.get(name='Project 1')
        p2 = Project.objects.get(name='Project 2')

        d1 = p1.devices.first()
        d2 = p2.devices.first()
        d3 = p2.devices.last()

        s1 = d1.streamids.first()
        s2 = d1.streamids.last()
        s3 = d2.streamids.first()
        s4 = d3.streamids.last()

        dt1 = timezone.now() - timedelta(minutes=60)

        data = [
            (s1.slug, dt1 + timedelta(seconds=10*60), 5),
            (s2.slug, dt1 + timedelta(seconds=15*60), 5),
            (s1.slug, dt1 + timedelta(seconds=20*60), 7),
            (s1.slug, dt1 + timedelta(seconds=25*60), 0),
            (s2.slug, dt1 + timedelta(seconds=30*60), 6),
            (s3.slug, dt1 + timedelta(seconds=35*60), 8),
            (s4.slug, dt1 + timedelta(seconds=40*60), 5),
            (s1.slug, dt1 + timedelta(seconds=45*60), 3),
            (s3.slug, dt1 + timedelta(seconds=50*60), 6),
        ]

        count = 0
        for item in data:
            StreamData.objects.create(
                stream_slug=item[0],
                timestamp=item[1],
                int_value=item[2],
                value=item[2] * 1.0,
                streamer_local_id=count
            )
            count += 1


class FactoryDeviceMock(BaseDeviceMock):
    """
    Mocks data for a Node connected to a Machine
    Includes:
    - DeviceTemplate and SensorGraph
    - Org and Project
    - Device and Streams
    - Basic Data
    """

    def __init__(self):
        super(FactoryDeviceMock, self).__init__('factory-machine1.json')

    def post_process(self):
        pass

    def testMock(self, testObj):
        testObj.assertEqual(Org.objects.count(), 3)
        testObj.assertEqual(DeviceTemplate.objects.count(), 1)
        testObj.assertEqual(ProjectTemplate.objects.count(), 1)
        testObj.assertEqual(SensorGraph.objects.count(), 1)
        testObj.assertEqual(Project.objects.count(), 2)
        testObj.assertEqual(VariableTemplate.objects.count(), 1)
        testObj.assertEqual(VarType.objects.count(), 1)
        testObj.assertEqual(Device.objects.count(), 1)
        testObj.assertEqual(Device.objects.first().template.id, DeviceTemplate.objects.first().id)
        testObj.assertEqual(StreamVariable.objects.count(), 1)
        testObj.assertEqual(StreamId.objects.count(), 1)
        testObj.assertEqual(StreamData.objects.count(), 149)


class SMTDeviceMock(BaseDeviceMock):
    """
    Mocks data for an SMT machine
    Includes:
    - DeviceTemplate and SensorGraph
    - Org and Project
    - Device and Streams
    - Basic Data
    """

    def __init__(self):
        super(SMTDeviceMock, self).__init__('smt-machine1.json')

    def post_process(self):
        pass

    def testMock(self, testObj):
        testObj.assertEqual(Org.objects.count(), 3)
        testObj.assertEqual(DeviceTemplate.objects.count(), 1)
        testObj.assertEqual(ProjectTemplate.objects.count(), 1)
        testObj.assertEqual(SensorGraph.objects.count(), 1)
        testObj.assertEqual(Project.objects.count(), 2)
        testObj.assertEqual(VariableTemplate.objects.count(), 1)
        testObj.assertEqual(VarType.objects.count(), 1)
        testObj.assertEqual(Device.objects.count(), 1)
        testObj.assertEqual(Device.objects.first().template.id, DeviceTemplate.objects.first().id)
        testObj.assertEqual(StreamVariable.objects.count(), 1)
        testObj.assertEqual(StreamId.objects.count(), 1)
        testObj.assertEqual(StreamData.objects.count(), 18)


class SMTDeviceMockGuad(BaseDeviceMock):
    """
    Guad data for an SMT machine
    Includes:
    - DeviceTemplate and SensorGraph
    - Org and Project
    - Device and Streams
    - Basic Data
    """

    def __init__(self):
        super(SMTDeviceMockGuad, self).__init__('smt-guad-c00.json')

    def post_process(self):
        pass

    def testMock(self, testObj):
        testObj.assertEqual(Org.objects.count(), 3)
        testObj.assertEqual(DeviceTemplate.objects.count(), 1)
        testObj.assertEqual(ProjectTemplate.objects.count(), 1)
        testObj.assertEqual(SensorGraph.objects.count(), 1)
        testObj.assertEqual(Project.objects.count(), 2)
        testObj.assertEqual(VariableTemplate.objects.count(), 1)
        testObj.assertEqual(VarType.objects.count(), 1)
        testObj.assertEqual(Device.objects.count(), 1)
        testObj.assertEqual(Device.objects.first().template.id, DeviceTemplate.objects.first().id)
        testObj.assertEqual(StreamVariable.objects.count(), 1)
        testObj.assertEqual(StreamId.objects.count(), 1)
        testObj.assertEqual(StreamData.objects.count(), 484)


class SMTDeviceMockSuzhou(BaseDeviceMock):
    """
    Suzhou data for an SMT machine
    Includes:
    - DeviceTemplate and SensorGraph
    - Org and Project
    - Device and Streams
    - Basic Data
    """

    def __init__(self):
        super(SMTDeviceMockSuzhou, self).__init__('smt-suzhou-c30.json')

    def post_process(self):
        pass

    def testMock(self, testObj):
        testObj.assertEqual(Org.objects.count(), 3)
        testObj.assertEqual(DeviceTemplate.objects.count(), 1)
        testObj.assertEqual(ProjectTemplate.objects.count(), 1)
        testObj.assertEqual(SensorGraph.objects.count(), 1)
        testObj.assertEqual(Project.objects.count(), 2)
        testObj.assertEqual(VariableTemplate.objects.count(), 1)
        testObj.assertEqual(VarType.objects.count(), 1)
        testObj.assertEqual(Device.objects.count(), 1)
        testObj.assertEqual(Device.objects.first().template.id, DeviceTemplate.objects.first().id)
        testObj.assertEqual(StreamVariable.objects.count(), 1)
        testObj.assertEqual(StreamId.objects.count(), 1)
        testObj.assertEqual(StreamData.objects.count(), 17)
