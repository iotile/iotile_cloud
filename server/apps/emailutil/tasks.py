import logging

from django.core.mail import EmailMultiAlternatives
from django.template.loader import get_template
from django.conf import settings
logger = logging.getLogger(__name__)


class Email(object):

    @classmethod
    def _render_template(self, template_name, ctx):
        return get_template(template_name).render(ctx)

    @classmethod
    def _get_txt_message(self, label, ctx):
        template_name = '{}/email.txt'.format(label)
        return self._render_template(template_name, ctx)

    @classmethod
    def _get_html_message(self, label, ctx):
        template_name = '{}/email.html'.format(label)
        return self._render_template(template_name, ctx)

    @classmethod
    def send_email(self, label, subject, ctx, emails, attachment=None):

        ctx['site_name'] = getattr(settings, 'SITE_NAME')

        txt_msg = self._get_txt_message(label, ctx)
        html_msg = self._get_html_message(label, ctx)

        if txt_msg and html_msg:
            msg = EmailMultiAlternatives(
                subject=subject,
                to=emails,
                body=txt_msg,
            )
            if attachment:
                msg.attach(attachment['filename'], attachment['content'], attachment['mimetype'])

            msg.attach_alternative(html_msg, "text/html")
            logger.info('Sending {0} email to {1}'.format(label, str(msg.to)))

            msg.send(fail_silently=False)
