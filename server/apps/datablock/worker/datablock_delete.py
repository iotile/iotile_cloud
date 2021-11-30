import json
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.devicelocation.models import DeviceLocation
from apps.emailutil.tasks import Email
from apps.org.models import OrgMembership
from apps.org.roles import ORG_ROLE_PERMISSIONS
from apps.property.models import GenericProperty
from apps.report.models import GeneratedUserReport
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError, WorkerActionSoftError
from apps.stream.models import StreamId
from apps.streamnote.models import StreamNote
from apps.utils.aws.sns import sns_staff_notification
from apps.utils.data_helpers.manager import DataManager
from apps.utils.data_mask.mask_utils import clear_data_mask
from apps.utils.gid.convert import int16gid

from ..models import DataBlock

logger = logging.getLogger(__name__)
user_model = get_user_model()

WORKER_QUEUE_NAME = getattr(settings, 'SQS_WORKER_QUEUE_NAME')


class DataBlockDeleteAction(Action):
    """
    This action will delete a DataBlock
    Including:
    - Deleting all device properties
    - Deleting all StreamData and StreamEventData
    - Deleting all StreamNote and DeviceLocations
    """
    _block = None
    _user = None

    @classmethod
    def _arguments_ok(self, args):
        return Action._check_arguments(
            args=args, task_name='DataBlockDeleteAction',
            required=['block_slug', 'user', ], optional=[]
        )

    def _delete_records(self):

        # 1. Delete all properties
        GenericProperty.objects.object_properties_qs(self._block).delete()

        # 2. Delete all Notes
        for s in self._block.streamids.all():
            notes_qs = StreamNote.objects.filter(target_slug=s.slug)
            notes_qs.delete()
        notes_qs = StreamNote.objects.filter(target_slug=self._block.slug)
        notes_qs.delete()

        # 3. Delete all Device Locations
        location_qs = DeviceLocation.objects.filter(target_slug=self._block.slug)
        location_qs.delete()

        # 4. Delete all Streams
        for s in self._block.streamids.all():
            data_qs = DataManager.filter_qs('data', stream_slug=s.slug)
            data_qs.delete()
            event_qs = DataManager.filter_qs('event', stream_slug=s.slug)
            event_qs.delete()
            s.delete()
        # Also delete Data Mask
        clear_data_mask(self._block, None, False)

        # 5. Delete all Generated Reports
        report_qs = GeneratedUserReport.objects.filter(source_ref=self._block.slug)
        report_qs.delete()

        # 6. Delete DataBlock itself
        self._block.delete()

    def _notify_user(self, slug, title, org):
        email = Email()
        ctx = {
            'slug': slug,
            'title': title,
            'url': org.get_webapp_url()
        }
        subject = 'IOTile Cloud Notification'
        emails = org.get_email_list(admin_only=True)
        try:
            email.send_email(label='datablock/delete', subject=subject, ctx=ctx, emails=emails)
        except Exception as e:
            logger.warning(str(e))
            # If the email failed, we want to try again, so we don't delete the SQS message
            raise WorkerActionSoftError(
                "Error when sending email. This task will be executed again after the default visibility timeout")

    def execute(self, arguments):
        super(DataBlockDeleteAction, self).execute(arguments)
        if DataBlockDeleteAction._arguments_ok(arguments):

            block_slug = arguments['block_slug']
            try:
                self._block = DataBlock.objects.get(slug=block_slug)
            except DataBlock.DoesNotExist:
                raise WorkerActionHardError("Device with slug {} not found!".format(block_slug))

            try:
                self._user = user_model.objects.get(slug=arguments['user'])
            except user_model.DoesNotExist:
                raise WorkerActionHardError("User with slug={} not found!".format(arguments['user']))

            # Cache information we will need for notifications
            title = self._block.title
            org = self._block.org

            # Do actual deleting
            self._delete_records()

            # Notify Org Admins
            self._notify_user(slug=block_slug, title=title, org=org)

            logger.info('DataBlock successfully deleted {}'.format(block_slug))

    @classmethod
    def schedule(cls, args=None, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        module_name = cls.__module__
        class_name = cls.__name__
        if DataBlockDeleteAction._arguments_ok(args):
            return super(DataBlockDeleteAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
        return None
