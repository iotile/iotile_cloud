
# from django.test import TestCase, Client
from unittest import TestCase

# DB1
from apps.authentication.models import Account
from apps.org.models import Org, OrgMembership
from apps.project.models import Project
from apps.physicaldevice.models import Device
from apps.stream.models import StreamId, StreamVariable, StreamSystemVariable
from apps.streamer.models import Streamer, StreamerReport
from apps.streamfilter.models import StreamFilter, StreamFilterAction, StreamFilterTrigger

# DB2
from apps.streamdata.models import StreamData
from apps.streamevent.models import StreamEventData

from .default import DefaultRouter
from .streamdata import StreamDataRouter
from .router_config import REDSHIFT_APPs


class DbRouteTestCase(TestCase):

    def testAppLabel(self):
        self.assertEqual(StreamData._meta.app_label, 'streamdata')
        self.assertEqual(StreamEventData._meta.app_label, 'streamevent')
        self.assertTrue('streamdata' in REDSHIFT_APPs)
        self.assertTrue('streamevent' not in REDSHIFT_APPs)
        self.assertFalse('auth' in REDSHIFT_APPs)

    def testDefaultDbForRead(self):
        router = DefaultRouter()
        # DB1
        self.assertEqual(router.db_for_read(Account), 'default')
        self.assertEqual(router.db_for_read(Org), 'default')
        self.assertEqual(router.db_for_read(OrgMembership), 'default')
        self.assertEqual(router.db_for_read(Project), 'default')
        self.assertEqual(router.db_for_read(Device), 'default')
        self.assertEqual(router.db_for_read(StreamId), 'default')
        self.assertEqual(router.db_for_read(StreamVariable), 'default')
        self.assertEqual(router.db_for_read(StreamSystemVariable), 'default')
        self.assertEqual(router.db_for_read(Streamer), 'default')
        self.assertEqual(router.db_for_read(StreamerReport), 'default')
        self.assertEqual(router.db_for_read(StreamFilter), 'default')
        self.assertEqual(router.db_for_read(StreamFilterAction), 'default')
        self.assertEqual(router.db_for_read(StreamFilterTrigger), 'default')
        self.assertEqual(router.db_for_read(StreamEventData), 'default')
        # DB2
        self.assertEqual(router.db_for_read(StreamData), None)

    def testDefaultDbForWrite(self):
        router = DefaultRouter()
        # DB1
        self.assertEqual(router.db_for_write(Account), 'default')
        self.assertEqual(router.db_for_write(Org), 'default')
        self.assertEqual(router.db_for_write(OrgMembership), 'default')
        self.assertEqual(router.db_for_write(Project), 'default')
        self.assertEqual(router.db_for_write(Device), 'default')
        self.assertEqual(router.db_for_write(StreamId), 'default')
        self.assertEqual(router.db_for_write(StreamVariable), 'default')
        self.assertEqual(router.db_for_write(StreamSystemVariable), 'default')
        self.assertEqual(router.db_for_write(Streamer), 'default')
        self.assertEqual(router.db_for_write(StreamerReport), 'default')
        self.assertEqual(router.db_for_write(StreamFilter), 'default')
        self.assertEqual(router.db_for_write(StreamFilterAction), 'default')
        self.assertEqual(router.db_for_write(StreamFilterTrigger), 'default')
        self.assertEqual(router.db_for_write(StreamEventData), 'default')
        # DB2
        self.assertEqual(router.db_for_write(StreamData), None)

    def testDefaultDbAllowRelation(self):
        router = DefaultRouter()
        self.assertTrue(router.allow_relation(obj1=Org, obj2=Project))
        self.assertTrue(router.allow_relation(obj1=Device, obj2=Project))
        self.assertTrue(router.allow_relation(obj1=StreamId, obj2=Project))
        self.assertTrue(router.allow_relation(obj1=Streamer, obj2=Device))
        self.assertFalse(router.allow_relation(obj1=Org, obj2=StreamData))
        self.assertFalse(router.allow_relation(obj1=Org, obj2=StreamData))
        self.assertFalse(router.allow_relation(obj1=StreamEventData, obj2=StreamData))

    def testDefaultDbAllowMigrate(self):
        router = DefaultRouter()
        # DB1
        self.assertTrue(router.allow_migrate(db='default', app_label='authentication'))
        self.assertTrue(router.allow_migrate(db='default', app_label='org'))
        self.assertTrue(router.allow_migrate(db='default', app_label='project'))
        self.assertTrue(router.allow_migrate(db='default', app_label='stream'))
        self.assertTrue(router.allow_migrate(db='default', app_label='physicaldevice'))
        self.assertTrue(router.allow_migrate(db='default', app_label='streamer'))
        self.assertTrue(router.allow_migrate(db='default', app_label='streamevent'))
        # DB2
        self.assertIsNone(router.allow_migrate(db='streamdata', app_label='streamdata'))

    def testStreamDataDbForRead(self):
        router = StreamDataRouter()
        # DB1
        self.assertEqual(router.db_for_read(Account), None)
        self.assertEqual(router.db_for_read(Org), None)
        self.assertEqual(router.db_for_read(OrgMembership), None)
        self.assertEqual(router.db_for_read(Project), None)
        self.assertEqual(router.db_for_read(Device), None)
        self.assertEqual(router.db_for_read(StreamId), None)
        self.assertEqual(router.db_for_read(StreamVariable), None)
        self.assertEqual(router.db_for_read(StreamSystemVariable), None)
        self.assertEqual(router.db_for_read(Streamer), None)
        self.assertEqual(router.db_for_read(StreamerReport), None)
        self.assertEqual(router.db_for_read(StreamFilter), None)
        self.assertEqual(router.db_for_read(StreamFilterAction), None)
        self.assertEqual(router.db_for_read(StreamFilterTrigger), None)
        self.assertEqual(router.db_for_read(StreamEventData), None)
        # DB2
        self.assertEqual(router.db_for_read(StreamData), 'streamdata')

    def testStreamDataDbForWrite(self):
        router = StreamDataRouter()
        # DB1
        self.assertEqual(router.db_for_write(Account), None)
        self.assertEqual(router.db_for_write(Org), None)
        self.assertEqual(router.db_for_write(OrgMembership), None)
        self.assertEqual(router.db_for_write(Project), None)
        self.assertEqual(router.db_for_write(Device), None)
        self.assertEqual(router.db_for_write(StreamId), None)
        self.assertEqual(router.db_for_write(StreamVariable), None)
        self.assertEqual(router.db_for_write(StreamSystemVariable), None)
        self.assertEqual(router.db_for_write(Streamer), None)
        self.assertEqual(router.db_for_write(StreamerReport), None)
        self.assertEqual(router.db_for_write(StreamFilter), None)
        self.assertEqual(router.db_for_write(StreamFilterAction), None)
        self.assertEqual(router.db_for_write(StreamFilterTrigger), None)
        self.assertEqual(router.db_for_write(StreamEventData), None)
        # DB2
        self.assertEqual(router.db_for_write(StreamData), 'streamdata')

    def testStreamDataDbAllowRelation(self):
        router = StreamDataRouter()
        self.assertFalse(router.allow_relation(obj1=Org, obj2=Project))
        self.assertFalse(router.allow_relation(obj1=Device, obj2=Project))
        self.assertFalse(router.allow_relation(obj1=StreamId, obj2=Project))
        self.assertFalse(router.allow_relation(obj1=Streamer, obj2=Device))
        self.assertFalse(router.allow_relation(obj1=Org, obj2=StreamData))
        self.assertFalse(router.allow_relation(obj1=Org, obj2=StreamData))
        self.assertFalse(router.allow_relation(obj1=StreamEventData, obj2=StreamData))

    def testStreamDataDbAllowMigrate(self):
        router = StreamDataRouter()
        # DB1
        self.assertIsNone(router.allow_migrate(db='default', app_label='authentication'))
        self.assertIsNone(router.allow_migrate(db='default', app_label='org'))
        self.assertIsNone(router.allow_migrate(db='default', app_label='project'))
        self.assertIsNone(router.allow_migrate(db='default', app_label='stream'))
        self.assertIsNone(router.allow_migrate(db='default', app_label='physicaldevice'))
        self.assertIsNone(router.allow_migrate(db='default', app_label='streamer'))
        self.assertIsNone(router.allow_migrate(db='default', app_label='streamevent'))
        # DB2
        self.assertTrue(router.allow_migrate(db='streamdata', app_label='streamdata'))
