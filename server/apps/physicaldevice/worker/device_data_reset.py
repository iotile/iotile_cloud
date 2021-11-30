import logging

import pytz

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.devicelocation.models import DeviceLocation
from apps.emailutil.tasks import Email
from apps.physicaldevice.models import Device
from apps.property.models import GenericProperty
from apps.report.models import GeneratedUserReport
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError, WorkerActionSoftError
from apps.stream.models import StreamId
from apps.streamfilter.dynamodb import DynamoFilterLogModel
from apps.streamnote.models import StreamNote
from apps.utils.data_helpers.manager import DataManager
from apps.utils.data_mask.mask_utils import clear_data_mask

logger = logging.getLogger(__name__)


class DeviceDataResetAction(Action):
    """
    This action will reset/clear a given Device
    Resetting is done by:
    - Deleting all device properties (if include_properties=True)
    - Deleting all StreamData and StreamEventData
    - Deleting all streamers and streamer reports (if full=True)
    - Delete Filter Logs
    """
    _device = None
    _full_reset = True
    _include_properties = True
    _include_notes_and_locations = True

    @classmethod
    def _arguments_ok(self, args):
        return Action._check_arguments(
            args=args, task_name='DeviceDataResetAction',
            required=['device_slug', 'user', ], optional=[
                'full', 'include_properties', 'include_notes_and_locations'
            ]
        )

    def _clear_properties(self):
        if self._include_properties:
            logger.info('Cloning Device Properties for {}'.format(self._device))
            assert(self._device)
            GenericProperty.objects.object_properties_qs(self._device, is_system=False).delete()

    def _clear_stream_data(self):
        logger.info('Deleting DataStreams and DataEventStreams for {}'.format(self._device))
        assert(self._device)
        stream_slugs = [s.slug for s in self._device.streamids.filter(block__isnull=True)]
        data_qs = DataManager.filter_qs('data', stream_slug__in=stream_slugs, device_slug=self._device.slug)
        data_qs.delete()
        event_qs = DataManager.filter_qs('event', stream_slug__in=stream_slugs, device_slug=self._device.slug)
        event_qs.delete()
        # Also delete Data Mask
        clear_data_mask(self._device, None, False)
        if self._full_reset:
            # Delete all data even if no StreamIds
            data_qs = DataManager.filter_qs(
                'data', device_slug=self._device.slug, project_slug=self._device.project.slug
            )
            data_qs.delete()
            event_qs = DataManager.filter_qs(
                'event', device_slug=self._device.slug, project_slug=self._device.project.slug
            )
            event_qs.delete()

    def _clear_streamers(self):
        logger.info('Deleting Streamers for {}'.format(self._device))
        assert self._device is not None
        # Delete all streamers reports
        for streamer in self._device.streamers.all():
            streamer.reports.all().delete()

        # Do not delete streamers unless this was a full reset
        if self._full_reset:
            logger.info('Full Device reset. Deleting streamers')
            self._device.streamers.all().delete()

    def _clear_notes_and_locations(self):
        if self._include_notes_and_locations:
            logger.info('Deleting DeviceLocations for {}'.format(self._device))
            assert self._device is not None

            stream_slugs = [s.slug for s in self._device.streamids.filter(block__isnull=True)]
            note_qs = StreamNote.objects.filter(target_slug__in=stream_slugs, type='ui')
            note_qs.delete()

            # Also delete notes to the device
            note_qs = StreamNote.objects.filter(target_slug=self._device.slug, type='ui')
            note_qs.delete()

            # Delete all device locations
            location_qs = DeviceLocation.objects.filter(target_slug=self._device.slug)
            location_qs.delete()

    def _delete_filter_logs(self):
        # Delete all filter logs
        try:
            with DynamoFilterLogModel.batch_write() as batch:
                for stream in self._device.streamids.all():
                    items = DynamoFilterLogModel.target_index.query(stream.slug)
                    for item in items:
                        batch.delete(item)
        except Exception as e:
            logger.error(str(e))

    def _delete_generated_reports(self):
        logger.info('Deleting GeneratedUserReport for {}'.format(self._device))
        assert self._device is not None

        # Delete all Generated Reports
        report_qs = GeneratedUserReport.objects.filter(source_ref=self._device.slug)
        report_qs.delete()

    def _notify_user(self, user):
        email = Email()
        ctx = {
            'device_slug': self._device.slug,
            'device_label': self._device.label,
            'url': settings.DOMAIN_BASE_URL + self._device.get_absolute_url(),
        }
        subject = 'IOTile Cloud Notification: Device Reset ({})'.format(self._device.slug)
        emails = [user.email, ]
        try:
            email.send_email(label='device/reset_confirmation', subject=subject, ctx=ctx, emails=emails)
        except Exception as e:
            logger.warning(str(e))
            # If the email failed, we want to try again, so we don't delete the SQS message
            raise WorkerActionSoftError(
                "Error when sending email. This task will be executed again after the default visibility timeout")

    def execute(self, arguments):
        super(DeviceDataResetAction, self).execute(arguments)
        if DeviceDataResetAction._arguments_ok(arguments):
            device_slug = arguments['device_slug']
            user_slug = arguments['user']
            self._full_reset = arguments.get('full', True)
            self._include_properties = arguments.get('include_properties', True)
            self._include_notes_and_locations = arguments.get('include_notes_and_locations', True)

            try:
                self._device = Device.objects.get(slug=device_slug)
            except Device.DoesNotExist:
                raise WorkerActionHardError("Device with slug {} not found !".format(device_slug))

            user_model = get_user_model()
            try:
                user = user_model.objects.get(slug=user_slug)
            except user_model.DoesNotExist:
                logger.error('User does not exist: {}'.format(user_slug))
                raise WorkerActionHardError('User not found: {}'.format(user_slug))

            if self._device.org and self._device.project:

                # 1. Delete all properties,
                self._clear_properties()

                # 2. Delete StreamData and StreamEventData
                #    Note that we are currently only deleting user data (with streamIds)
                #    and keeping all system data
                self._clear_stream_data()

                # 3. Delete Misc: Notes, Locations
                self._clear_notes_and_locations()

                # 4. Delete all streamers and streamer reports
                self._clear_streamers()

                # 5. Delete any generated reports
                self._delete_generated_reports()

                # 6. Delete Filter Logs
                self._delete_filter_logs()

                # 7. Notify User
                self._notify_user(user)

                # 8. Generate System Note
                StreamNote.objects.create(
                    target_slug=self._device.slug,
                    timestamp=timezone.now(),
                    note='Device data was cleared',
                    created_by=self._device.org.get_first_owner(),
                    type='si'
                )

                self._device.set_state('N1')
                self._device.save()
            else:
                raise WorkerActionHardError("Device with slug {} has no Org and/or Project !".format(device_slug))

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
        if DeviceDataResetAction._arguments_ok(args):
            return super(DeviceDataResetAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
        return None
