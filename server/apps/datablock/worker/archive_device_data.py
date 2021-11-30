import logging

import pytz

from django.conf import settings
from django.utils import timezone

from apps.datablock.models import DataBlock
from apps.devicelocation.models import DeviceLocation
from apps.emailutil.tasks import Email
from apps.physicaldevice.models import Device
from apps.property.models import GenericProperty
from apps.report.models import GeneratedUserReport
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError, WorkerActionSoftError
from apps.stream.models import StreamId
from apps.streamnote.models import StreamNote
from apps.utils.aws.sns import sns_staff_notification
from apps.utils.data_helpers.manager import DataManager
from apps.utils.gid.convert import formatted_gsid, gid_split
from apps.utils.iotile.variable import SYSTEM_VID

logger = logging.getLogger(__name__)


class ArchiveDeviceDataAction(Action):
    """
    This action will archive a given Device
    Archiving is done by:
    - Get expected DataBlock object (should be created by server before action is called)
    - Cloning all device properties and adding them to new block
    - Cloning all streams and adding them to the new block
    - Updating all StreamData, StreamEventData and StreamNotes with block's slug and stream slugs
    """

    _block = None
    _device = None

    @classmethod
    def _arguments_ok(self, args):
        return Action._check_arguments(
            args=args, task_name='ArchiveDeviceDataAction',
            required=['data_block_slug'], optional=['on_complete']
        )

    def _migrate_properties(self):
        logger.info('Migrating Device Properties for {}'.format(self._block))
        assert(self._device and self._block)
        # Migrate all user properties
        GenericProperty.objects.object_properties_qs(self._device, is_system=False).update(target=self._block.slug)
        # But copy system properties
        qs = GenericProperty.objects.object_properties_qs(self._device, is_system=True)
        for p in qs:
            GenericProperty.objects.clone(p, self._block.slug)

    def _clone_streams(self):
        logger.info('Cloning Stream Ids for {}'.format(self._block))
        assert(self._device and self._block)
        for s in self._device.streamids.filter(block__isnull=True, project=self._device.project):
            StreamId.objects.clone_into_block(s, self._block)

    def _migrate_stream_data(self):
        logger.info('Migrating DataStreams for {}'.format(self._block))
        assert(self._device and self._block)
        # original_device_slug = self._device.slug
        new_device_slug = self._block.original_device_slug
        # Assumes the _migrate_streams function has been called and new the block has streams
        for s in self._block.streamids.all():
            parts = gid_split(s.slug)
            old_stream_slug = self._device.get_stream_slug_for(parts[3])
            assert(s.slug != old_stream_slug)

            # This will not update any old data from another project
            # or any system data without a Stream Id object
            data_qs = DataManager.filter_qs('data', stream_slug=old_stream_slug)

            # Now do an update both the device and stream slugs
            data_qs.update(device_slug=new_device_slug, stream_slug=s.slug, project_slug='')

        # Also migrate data mask
        old_stream_slug = self._device.get_stream_slug_for(SYSTEM_VID['DEVICE_DATA_MASK'])
        new_stream_slug = self._block.get_stream_slug_for(SYSTEM_VID['DEVICE_DATA_MASK'])
        assert old_stream_slug != new_stream_slug
        # print(f'Migrating from {old_stream_slug} to {new_stream_slug}')
        data_qs = DataManager.filter_qs('event', stream_slug=old_stream_slug)
        data_qs.update(device_slug=new_device_slug, stream_slug=new_stream_slug, project_slug='')

    def _migrate_stream_events(self):
        logger.info('Migrating DataEventStreams for {}'.format(self._block))
        assert(self._device and self._block)
        # original_device_slug = self._device.slug
        new_device_slug = self._block.original_device_slug
        # Assumes the _migrate_streams function has been called and new the block has streams
        for s in self._block.streamids.all():
            parts = gid_split(s.slug)
            old_stream_slug = self._device.get_stream_slug_for(parts[3])
            assert(s.slug != old_stream_slug)

            # This will not update any old data from another project
            # or any system data without a Stream Id object
            events_qs = DataManager.filter_qs('event', stream_slug=old_stream_slug)

            # Now do an update both the device and stream slugs
            events_qs.update(device_slug=new_device_slug, stream_slug=s.slug, project_slug='')

    def _migrate_stream_notes(self):
        logger.info('Migrating DataNotes for {}'.format(self._block))
        assert(self._device and self._block)
        # original_device_slug = self._device.slug
        new_device_slug = self._block.original_device_slug
        # Assumes the _migrate_streams function has been called and new the block has streams
        for s in self._block.streamids.all():
            parts = gid_split(s.slug)
            old_stream_slug = self._device.get_stream_slug_for(parts[3])
            assert(s.slug != old_stream_slug)

            # This will not update any old data from another project
            # or any system data without a Stream Id object
            notes_qs = StreamNote.objects.filter(target_slug=old_stream_slug)

            # Now do an update with new target
            notes_qs.update(target_slug=s.slug)

        # Also migrate any notes to the device (but leave behind system notes
        notes_qs = StreamNote.objects.filter(target_slug=self._device.slug, type='ui')
        notes_qs.update(target_slug=self._block.slug)

    def _migrate_device_locations(self):
        logger.info('Migrating DeviceLocations for {}'.format(self._block))
        assert(self._device and self._block)
        # original_device_slug = self._device.slug
        new_device_slug = self._block.original_device_slug

        # Migrate all GPS Device Locations for device
        location_qs = DeviceLocation.objects.filter(target_slug=self._device.slug)
        location_qs.update(target_slug=self._block.slug)

    def _migrate_reports(self):
        logger.info('Migrating GeneratedReports for {}'.format(self._block))
        assert(self._device and self._block)

        # Migrate all Generated Reports
        report_qs = GeneratedUserReport.objects.filter(source_ref=self._device.slug)
        report_qs.update(source_ref=self._block.slug)

    def _notify_user(self):
        email = Email()
        ctx = {
            'device_slug': self._device.slug,
            'device_label': self._device.label,
            'block_title': self._block.title,
            'url': self._block.get_webapp_url(),
        }
        subject = 'IOTile Cloud Notification: New Archive ({})'.format(self._block.slug)
        # emails = self._device.org.get_email_list(admin_only=True)
        emails = [self._block.created_by.email, ]
        try:
            email.send_email(label='datablock/confirmation', subject=subject, ctx=ctx, emails=emails)
        except Exception as e:
            logger.warning(str(e))
            # If the email failed, we want to try again, so we don't delete the SQS message
            raise WorkerActionSoftError(
                "Error when sending email. This task will be executed again after the default visibility timeout")

    def _on_complete(self, args):
        if 'on_complete' in args and args['on_complete']:
            logger.info('On complete: {}'.format(args['on_complete']))
            if 'device' in args['on_complete'] and args['on_complete']['device']:
                device_args = args['on_complete']['device']
                if 'state' in device_args:
                    logger.info('Setting device {} to state={}'.format(self._device.slug, device_args['state']))
                    self._device.set_state(device_args['state'])
                if 'label' in device_args:
                    self._device.label = device_args['label']
        else:
            logger.info('No on_complete. Setting state to N1 for {}'.format(self._device.slug))
            self._device.set_state('N1')

        self._device.save()
        logger.info('Device {}: state={}, active={}'.format(
            self._device.slug, self._device.state, self._device.active)
        )

    def execute(self, arguments):
        super(ArchiveDeviceDataAction, self).execute(arguments)
        if ArchiveDeviceDataAction._arguments_ok(arguments):

            # 0. Find DataBlock and its Device
            #    IMPORTANT: Should be created by server before scheduling migration task
            try:
                self._block = DataBlock.objects.get(slug=arguments['data_block_slug'])
            except DataBlock.DoesNotExist:
                raise WorkerActionHardError("DataBlock with slug {} not found !".format(arguments['data_block_slug']))

            self._device = self._block.device
            # Copy SensorGraph to ensure we freeze it
            self._block.sg = self._device.sg

            # 1. Migrate all properties
            self._migrate_properties()

            # 2. Migrate Stream IDs, so any future changes do not affect the archive
            self._clone_streams()

            # 3. Update StreamData, StreamEventData and StreamNotes
            #    Note that different from the properties ans streams, are want to clean
            #    all data from the existing devices so all data/events are actually moved
            #    Notes and Locations as well
            #    Any generated user report with source_ref=device_slug
            self._migrate_stream_data()
            self._migrate_stream_events()
            self._migrate_stream_notes()
            self._migrate_device_locations()
            self._migrate_reports()

            self._block.completed_on = timezone.now()
            self._block.save()

            self._notify_user()

            StreamNote.objects.create(
                target_slug=self._device.slug,
                timestamp=timezone.now(),
                note='Device data was archived. Datablock ID: {}'.format(self._block.slug),
                created_by=self._block.created_by,
                type='si'
            )

            self._on_complete(arguments)

    @classmethod
    def schedule(cls, args, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        """
        schedule function should always have at least args and queue_name as arguments
        :param args:
        :param queue_name:
        :param delay_seconds: optional
        :return:
        """
        module_name = cls.__module__
        class_name = cls.__name__
        if ArchiveDeviceDataAction._arguments_ok(args):
            return super(ArchiveDeviceDataAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)

        sns_staff_notification('ArchiveDeviceDataAction arguments are not ok: {}'.format(args))
        return None
