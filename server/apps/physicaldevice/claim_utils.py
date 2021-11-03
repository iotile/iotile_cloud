import logging

from django.conf import settings
from django.utils import timezone

from apps.devicelocation.models import DeviceLocation
from apps.property.models import GenericProperty
from apps.report.models import GeneratedUserReport
from apps.stream.models import StreamId
from apps.streamfilter.dynamodb import DynamoFilterLogModel
from apps.streamnote.models import StreamNote
from apps.utils.data_helpers.manager import DataManager
from apps.utils.gid.convert import int16gid
from apps.verticals.utils import get_device_claim_vertical_helper

from .tasks import send_device_claim_notification, send_device_semiclaim_notification

logger = logging.getLogger(__name__)

DEFAULT_IOTILE_DEVICE_NAME_FORMAT = 'Device ({id})'


def generate_default_device_name(id):
    return DEFAULT_IOTILE_DEVICE_NAME_FORMAT.format(id=int16gid(id))


def create_streams_from_sensorgraph(device, created_by):
    project = device.project

    if project:
        # If the device has a sensor graph, and the sensor graph has variable templates, use that (New approach)
        # otherwise, create streams of ALL project variables

        # 1.- Check if device has SG
        sg = device.sg
        count = 0
        if sg:
            for var_t in sg.variable_templates.all():
                StreamId.objects.create_from_variable_template(
                    device=device, project=project, var_t=var_t, created_by=created_by)
                count += 1


def device_semiclaim(device, org):

    # 1.- Semi claim by setting org
    device.org = org
    device.save()

    # 2.- Notify Staff
    send_device_semiclaim_notification(device)


def device_claim(device, project, claimed_by):

    # 0.- Get application specific helper
    app_specif_helper = get_device_claim_vertical_helper(device)

    # 1.- Claim by setting a project and org
    device.project = project
    device.org = project.org
    device.claimed_on = timezone.now()
    device.claimed_by = claimed_by
    app_specif_helper.adjust_device()
    device.save()

    # 2.- Now create appropriate Streams
    #     Use VariableTemplates from the Sensor Graph if they exist
    create_streams_from_sensorgraph(device, device.claimed_by)

    # 3.- Make sure Project is setup for the specific app
    app_specif_helper.setup_project(project)

    # 4.- Make sure Org is setup for the specific app
    app_specif_helper.setup_org(project.org)

    # 5.- Notify Staff
    send_device_claim_notification(device)


def device_unclaim(device, label=None, clean_streams=False):
    msg = 'Device {0} has been marked as unclaimed.'.format(device.slug)

    # Delete all filter logs
    if getattr(settings, 'USE_DYNAMODB_FILTERLOG_DB'):
        try:
            with DynamoFilterLogModel.batch_write() as batch:
                for stream in device.streamids.all():
                    items = DynamoFilterLogModel.target_index.query(stream.slug)
                    for item in items:
                        batch.delete(item)
        except Exception as e:
            logger.error(str(e))

    if clean_streams:
        msg += ' {0} streams deleted.'.format(device.streamids.count())
        
        # Also delete StreamNote attached to this stream
        stream_slugs = [s.slug for s in device.streamids.filter(block__isnull=True)]
        note_qs = StreamNote.objects.filter(target_slug__in=stream_slugs, type='ui')
        note_qs.delete()

        device.streamids.filter(block__isnull=True).delete()

    # Delete all streamers reports (but not the streamer itself, as the last ID should be kept)
    for streamer in device.streamers.all():
        # This is just for cleanup
        logger.warning('TODO: Need to Delete ALL S3 Streamer Reports for  {0}'.format(streamer.slug))
        streamer.reports.all().delete()
        if clean_streams:
            # Also delete streamer
            streamer.delete()

    # Delete properties associated with this device
    GenericProperty.objects.object_properties_qs(device).delete()

    # Delete Notes and Locations
    StreamNote.objects.filter(target_slug=device.slug, type='ui').delete()
    DeviceLocation.objects.filter(target_slug=device.slug).delete()

    # Delete Generated Reports
    GeneratedUserReport.objects.filter(source_ref=device.slug).delete()

    if not label:
        label = generate_default_device_name(device.id)
    else:
        if '{id}' in label:
            label = label.format(id=int16gid(device.id))
    device.unclaim(label)

    # Delete data last in case we have issues deleting large data amounts
    # In which case, we just leave it behind in redshift
    if clean_streams:
        # Delete any available StreamData
        data_qs = DataManager.filter_qs('data', device_slug=device.slug)
        logger.info('Deleting {1} data entries for {0}'.format(device.slug, data_qs.count()))
        data_qs.delete()
        # Delete any available  StreamEventData
        event_qs = DataManager.filter_qs('event', device_slug=device.slug)
        logger.info('Deleting {1} event entries for {0}'.format(device.slug, event_qs.count()))
        event_qs.delete()

    logger.debug(msg)
    return msg
