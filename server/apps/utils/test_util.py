import datetime

from django.contrib.auth import get_user_model

from apps.component.models import Component
from apps.devicetemplate.models import DeviceSlot, DeviceTemplate
from apps.org.models import Org, OrgMembership
from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.projecttemplate.models import ProjectTemplate
from apps.sensorgraph.models import *
from apps.stream.models import StreamVariable

user_model = get_user_model()


class TestMixin(object):
    """
    Methods to help all or most Test Cases
    """

    """ User Fixture for testing """
    databases = '__all__'

    def usersTestSetup(self):
        self.u1 = user_model.objects.create_superuser(username='User1', email='user1@foo.com', password='pass')
        self.u1.is_active = True
        self.u1.save()
        self.u2 = self.create_user('User2', 'user2@foo.com', name="User Two")
        self.u3 = self.create_user('User3', 'user3@foo.com', name="User Three")

    def create_user(self, username, email, is_active=True, name=""):
        u = user_model.objects.create_user(username=username, email=email, password='pass')
        u.is_active = is_active
        u.name = name
        u.save()
        return u

    def userTestTearDown(self):
        user_model.objects.all().delete()

    """ Organization Fixture for testing """
    def orgTestSetup(self):
        """ usersTestSetup should be called before this function """
        self.o1 = Org.objects.create_org(name='Vendor', created_by=self.u1, is_vendor=True)
        self.o2 = Org.objects.create_org(name='Org 1', created_by=self.u2)
        self.o3 = Org.objects.create_org(name='Org 2', created_by=self.u3)

    def orgTestTearDown(self):
        Org.objects.all().delete()
        OrgMembership.objects.all().delete()

    """ Project and DeviceTemplate Fixture for testing """
    def projectTestSetup(self):
        """ usersTestSetup and orgTestSetup should be called before this function """
        self.pt1 = ProjectTemplate.objects.create(name='Default Template', org=self.o1,
                                                  created_by=self.u1)
        self.pt1_project = Project.objects.master_project_for_template(self.pt1)

        self.p1 = Project.objects.create(name='Project 1', project_template=self.pt1,
                                         created_by=self.u2, org=self.o2)
        self.p2 = Project.objects.create(name='Project 2', project_template=self.pt1,
                                         created_by=self.u3, org=self.o3)

    def projectTestTearDown(self):
        ProjectTemplate.objects.all().delete()
        Project.objects.all().delete()

    def deviceTemplateTestSetup(self):
        """ usersTestSetup and orgTestSetup should be called before this function """
        self.projectTemplateTestSetup()
        self.dt1 = DeviceTemplate.objects.create(external_sku='Device 1', org=self.o1, os_tag=1024,
                                                 os_major_version=0, os_minor_version=1,
                                                 released_on=datetime.datetime.utcnow(),
                                                 created_by=self.u1)
        self.dt2 = DeviceTemplate.objects.create(external_sku='Device 2', org=self.o1, os_tag=1025,
                                                 os_major_version=0, os_minor_version=1,
                                                 released_on=datetime.datetime.utcnow(),
                                                 created_by=self.u1)
        self.dt3 = DeviceTemplate.objects.create(external_sku='Device 3 1v.0', org=self.o1, os_tag=2048,
                                                 os_major_version=1, os_minor_version=0,
                                                 released_on=datetime.datetime.utcnow(),
                                                 created_by=self.u1)

        self.comp1 = Component.objects.create(external_sku='Component 1', org=self.o1, hw_tag='btc1_v3',
                                              created_by=self.u1)
        self.slot1 = DeviceSlot.objects.create(template=self.dt1, component=self.comp1, number=1)

    def deviceTemplateTestTearDown(self):
        DeviceSlot.objects.all().delete()
        Component.objects.all().delete()
        DeviceTemplate.objects.all().delete()
        self.projectTemplateTestTearDown()

    def projectTemplateTestSetup(self):
        self.projectTestSetup()
        """ usersTestSetup and orgTestSetup should be called before this function """
        self.pt2 = ProjectTemplate.objects.create(name='Project Template 2', org=self.o1,
                                                  created_by=self.u1)
        self.v0 = StreamVariable.objects.create_system_variable(
            name='Battery', created_by=self.u1, lid=0x5800,
        )
        self.pt1_v1 = StreamVariable.objects.create_variable(
            name='Var PT1 A', project=self.pt1_project, lid=0x5001, created_by=self.u2
        )

    def projectTemplateTestTearDown(self):
        ProjectTemplate.objects.all().delete()
        Project.objects.all().delete()
        StreamVariable.objects.all().delete()

    def createTestSensorGraph(self):
        assert self.o1
        assert self.u1
        w = VarType.objects.create(name='Gallons', storage_units_full='G', created_by=self.u1, stream_data_type='D0')
        self.gi = VarTypeInputUnit.objects.create(var_type=w, unit_full='Gal', unit_short='G',
                                             created_by=self.u1)
        self.go = VarTypeOutputUnit.objects.create(var_type=w, unit_full='Gal', unit_short='G',
                                              created_by=self.u1)
        sg1 = SensorGraph.objects.create(name='SG 1', major_version=1, app_tag=1027,
                                         app_major_version=0, app_minor_version=1,
                                         created_by=self.u1, org=self.o1)
        self.vartemp1 = VariableTemplate.objects.create(sg=sg1, created_by=self.u1, label='Var1',
                                        var_type=w, lid_hex='5001',
                                        default_input_unit=self.gi, default_output_unit=self.go)
        self.vartemp2 = VariableTemplate.objects.create(sg=sg1, created_by=self.u1, label='Var2',
                                        var_type=w, lid_hex='5002',
                                        default_input_unit=self.gi, default_output_unit=self.go)
        self.dwt = DisplayWidgetTemplate.objects.create(sg=sg1, created_by=self.u1, label='Widget 1')

        return sg1

    def create_basic_test_devices(self):
        self.sg1 = self.createTestSensorGraph()
        self.pd1 = Device.objects.create_device(project=self.p1, sg=self.sg1, label='d1', active=True,
                                                template=self.dt1, created_by=self.u2)
        self.pd2 = Device.objects.create_device(project=self.p2, sg=self.sg1, label='d2', active=True,
                                                template=self.dt1, created_by=self.u3)

    def sensorGraphTestTearDown(self):
        VarTypeInputUnit.objects.all().delete()
        VarTypeOutputUnit.objects.all().delete()
        VarType.objects.all().delete()
        VariableTemplate.objects.all().delete()
        DisplayWidgetTemplate.objects.all().delete()
        SensorGraph.objects.all().delete()
