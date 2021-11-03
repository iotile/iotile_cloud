from django.conf import settings
from django.utils.translation import gettext_lazy as _

from apps.emailutil.tasks import Email
from apps.emailutil.utils import EmailRecipientHelper
from apps.utils.data_helpers.manager import DataManager
from apps.utils.dynamic_loading import str_to_class


class ReportGenerator(object):
    _msgs = []
    _rpt = None
    _sources = None
    _start = None
    _end = None
    _reschedule_callback = None

    def __init__(self, msgs, rpt, start, end, sources=None):
        self._rpt = rpt
        self._start = start
        self._end = end
        self._msgs = msgs
        self.reschedule_callback = None
        if sources:
            self._sources = sources
        else:
            self._sources = rpt.sources

    def _compute_report_context(self):
        return {}

    def _email_template(self):
        return 'ERROR'

    def _get_email_list(self):
        helper = EmailRecipientHelper()
        recipients = self._rpt.notification_recipients
        emails = helper.get_emails_from_recipient_list(recipients=recipients, org=self._rpt.org)
        return emails

    def _get_stream_data_qs(self, stream_slug):
        qs = DataManager.filter_qs('data', stream_slug=stream_slug)
        if self._start:
            qs = qs.filter(timestamp__gte=self._start)
        if self._end:
            qs = qs.filter(timestamp__lt=self._end)
        return qs

    def _send_email(self, template, ctx, attachment=None):
        subject = _('IOTile Cloud Report: {}'.format(self._rpt.label))

        domain = getattr(settings, 'DOMAIN_BASE_URL')
        if len(self._msgs):
            ctx['msgs'] = self._msgs
        ctx['url'] = '{0}{1}'.format(domain, self._rpt.org.get_reports_url())

        emails = self._get_email_list()
        # Allow for the notification list to be empty, in which case, send no emails
        if len(emails):
            user_email = Email()
            user_email.send_email(
                label=template,
                subject=subject,
                ctx=ctx,
                emails=emails,
                attachment=attachment
            )

    def add_streams_for_qs(self, qs):
        assert True

    def process_config(self):
        pass

    def generate_user_report(self):
        """
        Given the data passed on the constructor, compute the report data
        and generate email template. Finally, send email to user.

        :return: Nothing
        """

        ctx = self._compute_report_context()
        template = self._email_template()

        # from pprint import pprint
        # pprint(ctx)

        self._send_email(template, ctx)

    def get_configuration_form_class(self):
        generator_name = self._rpt.generator
        module_path = '{0}.{1}.forms'.format(__package__, generator_name)
        parts = [part.capitalize() for part in generator_name.split('_')]
        class_name = '{}ConfigureForm'.format(''.join(parts))
        return str_to_class(module_path, class_name)

    @classmethod
    def _generator_package_path(cls, generator_name):
        module_path = '{0}.{1}.generator'.format(__package__, generator_name)
        parts = [part.capitalize() for part in generator_name.split('_')]
        class_name = '{}ReportGenerator'.format(''.join(parts))

        return module_path, class_name

    @classmethod
    def _generator_form_path(cls, generator_name):
        print(generator_name)
        module_path = '{0}.{1}.generator'.format(__package__, generator_name)
        print(module_path)
        parts = [part.capitalize() for part in generator_name.split('_')]
        class_name = '{}ConfigureForm'.format(''.join(parts))

        return module_path, class_name

    @classmethod
    def get_generator_class(cls, rpt):
        """
        Module and class name for derived ReportGenerator to use
        based on the report's format selection

        :param rpt: UserReport
        :return: module_path and class_name
        """
        module_path, class_name = cls._generator_package_path(rpt.generator)
        return str_to_class(module_path, class_name)

    @classmethod
    def get_generator_class_from_name(cls, name):
        """
        Module and class name for derived ReportGenerator to use
        based on the report's format selection

        :param rpt: UserReport
        :return: module_path and class_name
        """
        module_path, class_name = cls._generator_package_path(name)
        return str_to_class(module_path, class_name)
