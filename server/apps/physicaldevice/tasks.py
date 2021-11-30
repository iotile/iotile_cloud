import logging

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.streamnote.models import StreamNote
from apps.utils.aws.sns import sns_arc_slack_notification

from .worker.device_data_reset import DeviceDataResetAction

logger = logging.getLogger(__name__)


def send_device_action_notification(device, msg, user, create_note=True):
    site_name = settings.SITE_NAME
    url = settings.DOMAIN_BASE_URL + reverse('staff:device-detail', args=[device.id])

    if device.sg:
        sg_name = device.sg.name
    else:
        sg_name = 'Unk'

    txt_message = """
    FYI,

    *{msg}*:

    - Device: {slug}
    - User: {username}
    - Project: {project}
    - Org: {org}
    - App: {sg}
    - HW: {template}
    - Staff User Page: {url}

    """.format(site=site_name, slug=device.slug, username=str(user), msg=msg, template=str(device.template),
               project=str(device.project), org=str(device.org), url=url, sg=sg_name)

    if settings.PRODUCTION:
        sns_arc_slack_notification(txt_message)
    else:
        logger.info(txt_message)

    if create_note:
        StreamNote.objects.create(target_slug=device.slug, timestamp=timezone.now(), note=msg,
                                  type='si', created_by=user)


def send_device_claim_notification(device):
    user = device.claimed_by
    msg = 'A device has been claimed'
    send_device_action_notification(device=device, user=user, msg=msg, create_note=False)


def send_device_semiclaim_notification(device):
    user = device.claimed_by
    msg = 'A device has been semi-claimed'
    send_device_action_notification(device=device, user=user, msg=msg, create_note=False)


def schedule_reset(
        device, user, full_reset=False, include_properties=True, include_notes_and_locations=True
    ):
    if device:
        # 1. Set Device as busy
        device.set_state('B0')
        device.save()

        # 2. Schedule Resetting background task
        pid = DeviceDataResetAction.schedule(args={
            'device_slug': device.slug,
            'user': user.slug,
            'full': full_reset,
            'include_properties': include_properties,
            'include_notes_and_locations': include_notes_and_locations,
        })

        return pid

    return None
