import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage

from apps.org.models import Org
from apps.org.roles import ORG_ROLE_PERMISSIONS
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError

logger = logging.getLogger(__name__)

WORKER_QUEUE_NAME = getattr(settings, 'SQS_WORKER_QUEUE_NAME')


class OrgSendMessageAction(Action):

    @classmethod
    def _arguments_ok(self, args):
        return Action._check_arguments(
            args=args, task_name='OrgMessageAction',
            required=['user', 'org', 'role', 'subject', 'message'], optional=[]
        )

    def execute(self, arguments):
        super(OrgSendMessageAction, self).execute(arguments)
        if OrgSendMessageAction._arguments_ok(arguments):

            user_slug = arguments['user']
            org_slug = arguments['org']
            role = arguments['role']
            subject = arguments['subject']
            message = arguments['message']

            if role != '-' and role not in ORG_ROLE_PERMISSIONS:
                logger.error('Illegal role: {}'.format(role))
                raise WorkerActionHardError('Illegal Orgmembership role: {}'.format(role))

            user_model = get_user_model()
            try:
                user = user_model.objects.get(slug=user_slug)
            except user_model.DoesNotExist:
                logger.error('User does not exist: {}'.format(user_slug))
                raise WorkerActionHardError('User not found: {}'.format(user_slug))

            try:
                org = Org.objects.get(slug=org_slug)
            except Org.DoesNotExist:
                logger.error('Org does not exist: {}'.format(org_slug))
                raise WorkerActionHardError('Org not found: {}'.format(org_slug))

            # Add disclaimer to make it clear who this is from
            message += '\n\n-----------------------\n'
            message += 'DO NOT REPLY TO THIS EMAIL\n\n'
            message += 'This message is sent on behalf of {} ({}), an admin for {}\n\n'.format(
                user.name if user.name else user,
                user.email,
                org.name
            )
            message += 'Thank you for using {}!\n'.format(getattr(settings, 'SITE_NAME'))

            if role == '-':
                # All members
                members = org.membership.filter(is_active=True, user__is_active=True)
            else:
                members = org.membership.filter(role=role, is_active=True, user__is_active=True)

            for membership in members:
                logger.info('Email to {}'.format(membership.user.email))

                email = EmailMessage(
                    subject=subject,
                    body=message,
                    to=[membership.user.email, ],
                )
                email.send(fail_silently=True)

    @classmethod
    def schedule(cls, args=None, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        module_name = cls.__module__
        class_name = cls.__name__
        if OrgSendMessageAction._arguments_ok(args):
            super(OrgSendMessageAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
