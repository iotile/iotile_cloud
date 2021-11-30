from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.configattribute.models import ConfigAttribute
from apps.org.models import Org
from apps.physicaldevice.claim_utils import *
from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.sensorgraph.models import SensorGraph
from apps.stream.models import StreamId, StreamVariable
from apps.streamfilter.models import StreamFilter
from apps.utils.test_util import TestMixin
from apps.utils.utest.devices import TripDeviceMock

user_model = get_user_model()


class DeviceUtilsTestCase(TestMixin, TestCase):

    def setUp(self):
        self.assertEqual(Device.objects.count(), 0)
        self.usersTestSetup()

        self.device_mock = TripDeviceMock()

        self.o2 = Org.objects.get(slug='user-org')
        self.p1 = Project.objects.get(name='Project 1')
        self.pd1 = self.p1.devices.first()

    def tearDown(self):
        StreamVariable.objects.all().delete()
        StreamId.objects.all().delete()
        StreamFilter.objects.all().delete()
        self.orgTestTearDown()
        self.userTestTearDown()
        self.device_mock.tearDown()

    def testMock(self):
        self.device_mock.testMock(self)

    def testShippingDeviceClaim(self):
        sg = self.pd1.sg
        self.assertTrue('Shipping' in sg.name)
        self.assertTrue('POD-1M' in self.pd1.template.family)
        pd2 = Device.objects.create(id=1, label="d1", template=self.pd1.template, sg=sg, created_by=self.u1)
        self.assertTrue('shipping' in pd2.sg.slug.split('-'))
        pd3 = Device.objects.create(id=3, label="d3", template=self.pd1.template, sg=sg, created_by=self.u1)

        org = Org.objects.create_org(name='New Org', created_by=self.u2)
        p_new = Project.objects.create(name='Project 1', created_by=self.u2, org=org)

        self.assertEqual(p_new.stream_filters.count(), 0)
        self.assertEqual(ConfigAttribute.objects.filter(target='^new-org').count(), 0)

        device_claim(device=pd2, project=p_new, claimed_by=self.u2)
        d1 = Device.objects.get(pk=pd2.id)
        self.assertEqual(d1.project, p_new)
        self.assertEqual(d1.org, pd2.org)
        self.assertEqual(d1.claimed_by, self.u2)
        self.assertEqual(d1.streamids.count(), 9)
        self.assertEqual(sg.variable_templates.count(), d1.streamids.count())
        self.assertEqual(p_new.streamids.count(), 9)

        # Check that device is setup for Shipping and it is inactive
        self.assertEqual(d1.state, 'N0')
        self.assertEqual(d1.label, 'POD-1M[ae1] [{}]'.format(d1.slug))

        # Check that project was setup for shipping
        p_new = Project.objects.get(pk=p_new.id)
        self.assertTrue('shipping' in p_new.project_template.slug)
        self.assertEqual(p_new.stream_filters.count(), 3)
        f1 = p_new.stream_filters.first()
        f1.name = 'different name'
        f1.save()

        # Check that org was setup for shipping
        self.assertEqual(ConfigAttribute.objects.filter(target='^new-org').count(), 5)

        device_claim(device=pd3, project=p_new, claimed_by=self.u2)
        d3 = Device.objects.get(pk=pd3.id)
        self.assertEqual(d3.project, p_new)
        self.assertEqual(d3.org, pd2.org)
        self.assertEqual(d3.claimed_by, self.u2)
        self.assertEqual(d3.streamids.count(), 9)
        self.assertEqual(p_new.streamids.count(), 18)
        self.assertEqual(p_new.stream_filters.count(), 3)
