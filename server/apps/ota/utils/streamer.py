import logging
import struct

import structpp

from apps.devicetemplate.models import DeviceTemplate
from apps.sensorgraph.models import SensorGraph
from apps.sqsworker.exceptions import WorkerInternalError
from apps.streamnote.models import StreamNote
from apps.utils.aws.sns import sns_staff_notification
from apps.utils.iotile.variable import SYSTEM_VID
from apps.utils.timezone_utils import convert_to_utc

from ..models import DeploymentAction, DeploymentRequest, DeviceVersionAttribute

logger = logging.getLogger(__name__)


class DeploymentActionStreamerHelper(object):
    _device = None
    _os_tag_vid = SYSTEM_VID['OS_TAG_VERSION']
    _app_tag_vid = SYSTEM_VID['APP_TAG_VERSION']

    def __init__(self, device):
        self._device = device

    def _version_tag_type(self, vid):
        return 'os' if vid == self._os_tag_vid else 'app'

    def _log_error(self, e):
        msg = 'Unable to decode tag and version: {} (Device {})'.format(e, self._device.slug)
        sns_staff_notification(msg)
        logger.error(msg)

    def _decode_value(self, value):
        """
        Decode StreamData value to get:

        - 20bit Tag
        - 6bit: Minor Version
        - 6bit: Major Version

        :param value: StreamData with encoded value
        :return: tag,major,minor
        """
        unpack_format = '<L{tag: 20, minor: 6, major: 6}'

        try:
            packed = struct.pack("<L", value)
            obj = structpp.unpack(unpack_format, packed, asdict=True)
            return obj['tag'], obj['major'], obj['minor']
        except Exception as e:
            self._log_error('Unable to decode tag and version: {}'.format(e))
            return None, None, None

    def complete_action(self, vid, data):
        logger.info('Completing Deployment Action for {} (vid={})'.format(self._device, vid))
        version_tag_type = self._version_tag_type(vid)
        user_note = 'Device {} has been updated:'.format(self._device.slug)

        # 0. Decode data value to extract tag and version
        tag, major, minor = self._decode_value(data.int_value)
        if tag is None or major is None or minor is None:
            # Unable to decode tag and version
            return

        if vid == self._app_tag_vid and tag == 0 and major == 0 and minor == 0:
            # This SG is from before we had tags implemented. Ignore
            return

        if vid == self._os_tag_vid and tag == 1024 and major == 0 and minor == 0:
            # This OS is from before we had tags implemented. Ignore
            return

        logger.info('==> Got {} Tag {}, v{}.{}'.format(version_tag_type, tag, major, minor))

        # 0. Get any previous Version Attribute to check if the update is different
        #    Ignore if not
        last_version = DeviceVersionAttribute.objects.last_device_version(device=self._device, type=version_tag_type)
        if last_version:
            if last_version.tag == tag and last_version.major_version == major and last_version.minor_version == minor:
                # Device sent an update, but nothing has changed. We need to ignore
                logger.info('==> Ignoring Device OTA Update. No change')
                return

        # 1. Create a new Version Attribute for this device
        try:
            logger.info('Creating New Version Attribute')
            version_attribute = DeviceVersionAttribute.objects.create(
                device=self._device, type=version_tag_type, tag=tag,
                major_version=major, minor_version=minor,
                streamer_local_id=data.streamer_local_id,
                updated_ts=convert_to_utc(data.timestamp)
            )
            logger.info('==> New version attribute: {}'.format(version_attribute))
        except Exception as err:
            self._log_error('Unable to create version attribute: {}'.format(err))
            return

        # 2. Update Device with new Device Template or Sensor Graph
        if vid == self._os_tag_vid:

            # 2a. Update Device Template
            template_qs = DeviceTemplate.objects.filter(
                os_tag=tag,
                os_major_version=major,
                os_minor_version=minor,
                active=True
            ).order_by('major_version', 'minor_version', 'patch_version')
            new_template = template_qs.last()
            if not new_template:
                # TODO: Remove following hack to handle case when existing template has no tag versions set
                template_qs = DeviceTemplate.objects.filter(
                    os_tag=tag,
                    active=True
                ).order_by('major_version', 'minor_version', 'patch_version')
                new_template = template_qs.last()
                msg = 'Found unknown OS tag (with exact version): {} v{}.{}, Device: {} (Using last version found)'.format(
                    tag, major, minor, self._device.slug
                )
                sns_staff_notification(msg)
            if new_template:
                self._device.template = new_template
                user_note += '\n- New Device Template: {} {}'.format(new_template.name, new_template.version)
            else:
                raise WorkerInternalError('Found unknown tag (no device template found): {} v{}.{}, Device: {}'.format(
                    tag, major, minor, self._device.slug))

        if vid == self._app_tag_vid:

            # 2b. Update Sensor Graph
            sg_qs = SensorGraph.objects.filter(
                app_tag=tag,
                app_major_version=major,
                app_minor_version=minor,
                active=True
            ).order_by('major_version', 'minor_version', 'patch_version')
            new_sg = sg_qs.last()
            if not new_sg:
                # TODO: Remove following hack to handle case when existng template has no tag versions set
                sg_qs = SensorGraph.objects.filter(
                    app_tag=tag,
                    active=True
                ).order_by('major_version', 'minor_version', 'patch_version')
                new_sg = sg_qs.last()
                msg = 'Found unknown SG tag (with exact version): {} v{}.{}, Device={} (Using last version found)'.format(
                    tag, major, minor, self._device.slug
                )
                sns_staff_notification(msg)
            if new_sg:
                self._device.sg = new_sg
                user_note += '\n- New Sensor Graph: {} {}'.format(new_sg.name, new_sg.version)
            else:
                raise WorkerInternalError('Found unknown tag (no sensor graph found): {} v{}.{}, Device={}'.format(
                    tag, major, minor, self._device.slug))

        # 3. Commit device changes
        self._device.save()

        # 4. Update deployment request/action as needed
        # NOTE that a developer could have updated the device without the cloud involved
        #      so it is ok if there is no deployment request at all
        deployment_request = None
        action_qs = self._device.deployment_actions.filter(device_confirmation=False, attempt_successful=True).order_by('last_attempt_on')
        deployment_action = action_qs.last()
        if deployment_action:
            deployment_action.device_confirmation = True
            user_note += '\n- Deployment Action {} has been set to complete'.format(deployment_action.id)
            if deployment_action.log:
                deployment_action.log = deployment_action.log + '\n' + user_note
            else:
                deployment_action.log = user_note
            deployment_action.save()

            # If we find an action, then get the deployment request associated to it
            deployment_request = deployment_action.deployment

        if not deployment_request:
            # If we did not find a deployment action and therefore no deployment request
            # assume this could have been because the mobile/gateway was unable to register
            # the action. Yet, the device got updated somehow, so lets check if there was
            # a deployment request
            deployment_qs = DeploymentRequest.objects.device_deployments_qs(
                self._device, released=True
            ).order_by('released_on')
            deployment_request = deployment_qs.first()

        if deployment_request and not deployment_action:
            # Assuming we found a deployment request but there was no action associated to it
            # create one
            logger.warning('==> Deployment: {} had no associated action. Yet, the device was updated'.format(deployment_request))
            try:
                user_note += '\n- Deployment Action auto created by IOTile Cloud'
                DeploymentAction.objects.create(
                    deployment=deployment_request,
                    device=self._device,
                    attempt_successful=True,
                    device_confirmation=True,
                    log=user_note
                )
            except Exception as err:
                self._log_error('Unable to create DeploymentAction: {}'.format(err))

        # Log update as a device note
        # print(user_note)
        created_by = deployment_request.created_by if deployment_request and deployment_request.created_by else self._device.claimed_by
        if not created_by:
            # Last resource, assign note to person that created the Org
            created_by = self._device.org.created_by

        try:
            logger.info('Stream note generated for OTA update')
            StreamNote.objects.create(
                target_slug=self._device.slug,
                type='si',
                timestamp=convert_to_utc(data.timestamp),
                note=user_note,
                created_by=created_by
            )
        except Exception as e:
            self._log_error('Unable to create StreamNote: {}'.format(e))
