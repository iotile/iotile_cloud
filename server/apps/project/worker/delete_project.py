import logging

from django.conf import settings
from django.contrib.auth import get_user_model

from apps.emailutil.tasks import Email
from apps.org.models import Org
from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError, WorkerActionSoftError
from apps.stream.models import StreamId, StreamVariable
from apps.streamnote.models import StreamNote
from apps.utils.data_helpers.manager import DataManager

logger = logging.getLogger(__name__)
user_model = get_user_model()


class ProjectDeleteAction(Action):
    """
    This action will delete the project as well as its associated variables, streams, and data streams
    Actions:
    - Deleting all StreamVariable points of the project
    - Deleting all StreamId points of the project
    - Deleting all StreamData points of the project
    """
    _project = None
    _user = None
    _logs = []

    @classmethod
    def _arguments_ok(self, args):
        return Action._check_arguments(
            args=args,
            task_name='ProjectDeleteAction',
            required=[
                'user',
                'project_slug',
            ],
            optional=[],
        )

    def _log_and_delete(self, queryset, message):
        logger.info(message)
        self._logs.append(message)
        queryset.delete()

    def _delete_data(self):
        logger.info('Deleting StreamVariables, StreamIds, and StreamData for {}'.format(self._project))
        assert self._project

        variables_qs = StreamVariable.objects.filter(project=self._project)
        streams_qs = StreamId.objects.filter(project=self._project, block__isnull=True)

        stream_slugs = [s.slug for s in streams_qs]
        data_qs = DataManager.filter_qs('data', stream_slug__in=stream_slugs)
        event_qs = DataManager.filter_qs('event', stream_slug__in=stream_slugs)
        notes_qs = StreamNote.objects.filter(target_slug=self._project.slug, type='ui')
        project_qs = Project.objects.filter(id=self._project.id)

        self._log_and_delete(variables_qs, '{} variables deleted'.format(variables_qs.count()))
        self._log_and_delete(streams_qs, '{} streams deleted'.format(streams_qs.count()))
        self._log_and_delete(data_qs, '{} data streams deleted'.format(data_qs.count()))
        self._log_and_delete(event_qs, '{} stream events deleted'.format(event_qs.count()))
        self._log_and_delete(notes_qs, '{} stream notes deleted'.format(notes_qs.count()))
        self._log_and_delete(project_qs, 'Project {} has been deleted'.format(self._project.name))

    def _notify_user(self):
        email = Email()
        ctx = {
            'project_name': self._project.name,
            'project_slug': self._project.slug,
            'username': self._user.username,
            'logs': self._logs,
        }
        subject = 'IOTile Cloud Notification'
        # Send notification to admins plus 
        emails = self._project.org.get_email_list(admin_only=True)
        emails.append(self._user.email)
        try:
            email.send_email(label='project/delete_confirmation', subject=subject, ctx=ctx, emails=emails)
        except Exception as e:
            logger.warning(str(e))
            # If the email failed, we want to try again, so we don't delete the SQS message
            raise WorkerActionSoftError(
                'Error when sending email. This task will be executed again after the default visibility timeout'
            )

    def _notify_failure(self):
        email = Email()
        ctx = {
            'project': self._project,
            'username': self._user.username,
            'devices': Device.objects.filter(project=self._project.id),
        }
        subject = 'IOTile Cloud Notification'
        # Only send notification to user that initiated task
        emails = [self._user.email]
        try:
            email.send_email(label='project/delete_failure', subject=subject, ctx=ctx, emails=emails)
        except Exception as e:
            logger.warning(str(e))
            # If the email failed, we want to try again, so we don't delete the SQS message
            raise WorkerActionSoftError(
                'Error when sending email. This task will be executed again after the default visibility timeout'
            )

    def execute(self, arguments):
        super(ProjectDeleteAction, self).execute(arguments)
        if ProjectDeleteAction._arguments_ok(arguments):
            self._logs = []

            try:
                self._project = Project.objects.get(slug=arguments['project_slug'])
            except Project.DoesNotExist:
                raise WorkerActionHardError("Project with slug {} not found!".format(arguments['project_slug']))

            try:
                self._user = user_model.objects.get(slug=arguments['user'])
            except user_model.DoesNotExist:
                raise WorkerActionHardError("User {} not found !".format(arguments['user']))

            # Check that no devices are claimed under this project
            if not self._project.devices.exists():
                # 1. Delete the project as well as its variables, streams, data streams, stream events, and notes
                self._delete_data()

                if len(self._logs) == 0:
                    self._logs.append('No data deleted')

                # 2. Notify User
                self._notify_user()

            else:
                # If there are devices claimed under the project, send email notifying that no operation was done
                self._notify_failure()

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
        if ProjectDeleteAction._arguments_ok(args):
            super(ProjectDeleteAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
