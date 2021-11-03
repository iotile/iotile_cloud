import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from iotile_cloud.utils.gid import IOTileVariableSlug

from apps.emailutil.tasks import Email
from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError, WorkerActionSoftError
from apps.stream.models import StreamVariable, StreamId
from apps.streamnote.models import StreamNote
from apps.utils.data_helpers.manager import DataManager
from apps.physicaldevice.claim_utils import create_streams_from_sensorgraph
from apps.utils.gid.convert import int16gid

logger = logging.getLogger(__name__)


class DeviceMoveAction(Action):
    """
    This action will move the device from one Project to another
    and optionally move the data associated with the device
    Move is done by:
    - Setting device project to new project
    - If selected, update all data with new project, variable and stream slugs
    """
    _user = None
    _device = None
    _move_data = False
    _src_project = None
    _dst_project = None

    @classmethod
    def _arguments_ok(cls, args):
        return Action._check_arguments(
            args=args, task_name='DeviceMoveAction',
            required=['device_slug', 'project_slug', 'user', ], optional=['move_data', ]
        )

    def _move_stream_data(self):
        logger.info(f'Moving data for {self._device.slug} to {self._dst_project.slug}')
        assert(self._device)
        for stream in self._device.streamids.filter(block__isnull=True, project=self._src_project):
            new_project_slug = self._dst_project.slug
            new_variable_slug = str(IOTileVariableSlug(id=stream.var_lid, project=new_project_slug))
            new_stream_slug = str(self._device.get_stream_slug_for(int16gid(stream.var_lid)))
            data_qs = DataManager.filter_qs('data', stream_slug=stream.slug, device_slug=self._device.slug)
            data_qs.update(project_slug=new_project_slug, stream_slug=new_stream_slug, variable_slug=new_variable_slug)
            event_qs = DataManager.filter_qs('event', stream_slug=stream.slug, device_slug=self._device.slug)
            event_qs.update(project_slug=new_project_slug, stream_slug=new_stream_slug, variable_slug=new_variable_slug)

    def _move_notes(self):
        logger.info(f'Moving Notes for {self._device.slug} to {self._dst_project.slug}')
        assert(self._device)
        for stream in self._device.streamids.filter(block__isnull=True, project=self._src_project):
            new_stream_slug = str(self._device.get_stream_slug_for(int16gid(stream.var_lid)))
            note_qs = StreamNote.objects.filter(target_slug=stream.slug)
            note_qs.update(target_slug=new_stream_slug)

    def _move_stream_ids(self):
        """
        Move all StreamId records to the new project
        If needed, create new variables on new project
        """
        logger.info(f'Moving StreamIDs for {self._device.slug} to {self._dst_project.slug}')
        assert(self._device)

        # Create Variables in new project (if needed)
        # and keep a map so we can update stream.variable below
        variables = {}
        sg = self._device.sg
        if sg:
            for var_t in sg.variable_templates.all():
                var = StreamVariable.objects.create_from_variable_template(
                    project=self._dst_project, var_t=var_t, created_by=self._user
                )
                variables[var.lid] = var

        for stream in self._device.streamids.filter(block__isnull=True, project=self._src_project):
            stream.project = self._dst_project
            if stream.var_lid in variables:
                stream.variable = variables[stream.var_lid]
            else:
                stream.variable = None
            # Update the stream slug based on Project, Block, Device and Variable
            stream.update_slug_from_parts()
            try:
                stream = StreamId.objects.get(slug=stream.slug)
            except StreamId.DoesNotExist:
                # Only change stream if it does not already exist on new project
                stream.save()

    def _notify_user(self):
        email = Email()
        ctx = {
            'device_slug': self._device.slug,
            'device_label': self._device.label,
            'src_project_slug': self._src_project.slug,
            'src_project_name': self._src_project.name,
            'dst_project_slug': self._dst_project.slug,
            'dst_project_name': self._dst_project.name,
            'url': settings.DOMAIN_BASE_URL + self._device.get_absolute_url(),
        }
        subject = 'IOTile Cloud Notification: Device Move ({})'.format(self._device.slug)
        emails = [self._user.email, ]
        try:
            email.send_email(label='device/move_confirmation', subject=subject, ctx=ctx, emails=emails)
        except Exception as e:
            logger.warning(str(e))
            # If the email failed, we want to try again, so we don't delete the SQS message
            raise WorkerActionSoftError(
                "Error when sending email. This task will be executed again after the default visibility timeout")

    def execute(self, arguments):
        super(DeviceMoveAction, self).execute(arguments)
        if DeviceMoveAction._arguments_ok(arguments):
            device_slug = arguments['device_slug']
            project_slug = arguments['project_slug']
            user_slug = arguments['user']
            self._move_data = arguments.get('move_data', False)

            try:
                self._device = Device.objects.get(slug=device_slug)
            except Device.DoesNotExist:
                raise WorkerActionHardError("Device with slug {} not found !".format(device_slug))

            self._src_project = self._device.project

            try:
                self._dst_project = Project.objects.get(slug=project_slug)
            except Project.DoesNotExist:
                raise WorkerActionHardError("Project with slug {} not found !".format(project_slug))

            if self._src_project.org != self._dst_project.org:
                raise WorkerActionHardError('src and dst projects not part of same Org')

            user_model = get_user_model()
            try:
                self._user = user_model.objects.get(slug=user_slug)
            except user_model.DoesNotExist:
                logger.error('User does not exist: {}'.format(user_slug))
                raise WorkerActionHardError('User not found: {}'.format(user_slug))

            if self._device.org and self._device.project:

                # 1.- Move by setting a project and org
                self._device.project = self._dst_project
                self._device.org = self._dst_project.org
                self._device.save()

                # 2.- If needed, move data
                if self._move_data:  
                    self._move_stream_data()
                    self._move_notes()

                # 3.- Now move (or create) appropriate Streams on new Project
                #     Use VariableTemplates from the Sensor Graph if they exist
                if self._move_data:
                    # if we are moving the data, also move the streams
                    self._move_stream_ids()
                else:
                    owner = self._device.claimed_by if self._device.claimed_by else self._device.created_by
                    create_streams_from_sensorgraph(self._device, owner)

                # 4. Notify User
                self._notify_user()

                # 5. Generate System Note
                StreamNote.objects.create(
                    target_slug=self._device.slug,
                    timestamp=timezone.now(),
                    note='Device was moved from {} to {}'.format(self._src_project.slug, self._dst_project.slug),
                    created_by=self._user,
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
        if DeviceMoveAction._arguments_ok(args):
            return super(DeviceMoveAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
        return None
