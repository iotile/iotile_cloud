import time
import logging

from django.conf import settings
from django.template.defaultfilters import slugify
from django.urls import reverse

from apps.utils.aws.sns import sns_arc_slack_notification

# Get an instance of a logger
logger = logging.getLogger(__name__)


def send_new_user_notification(id, username, email):
    site_name = settings.SITE_NAME
    url = settings.DOMAIN_BASE_URL + reverse('staff:user-detail', args=[slugify(username)])

    txt_message = """
    FYI,

    *A new user has registered*:

    - Username: {username}
    - Email: {email}
    - Staff User Page: {url}
    
    """.format(username=username, email=email, site=site_name, url=url)

    if settings.PRODUCTION:
        sns_arc_slack_notification(txt_message)
    else:
        logger.info(txt_message)


