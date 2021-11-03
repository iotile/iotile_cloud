import time
import logging

from django.conf import settings
from django.urls import reverse

from apps.utils.aws.sns import sns_arc_slack_notification

# Get an instance of a logger
logger = logging.getLogger(__name__)


def send_new_org_notification(org):
    url = settings.DOMAIN_BASE_URL + reverse('staff:org-detail', args=[org.slug])

    txt_message = """
    FYI,

    *A new organization has been created*:

    - Name: {name}
    - Template: {ot}
    - Staff Org Page: {url}
    
    """.format(name=org.name, ot=org.ot, url=url)

    if settings.PRODUCTION:
        sns_arc_slack_notification(txt_message)
    else:
        logger.info(txt_message)


