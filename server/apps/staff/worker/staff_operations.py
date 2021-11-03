import logging
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.datablock.models import DataBlock
from apps.devicetemplate.models import DeviceTemplate
from apps.emailutil.tasks import Email
from apps.org.models import Org, OrgMembership
from apps.org.roles import ORG_ROLE_PERMISSIONS
from apps.physicaldevice.claim_utils import device_unclaim
from apps.physicaldevice.models import Device
from apps.sensorgraph.models import SensorGraph
from apps.sqsworker.action import Action
from apps.sqsworker.exceptions import WorkerActionHardError
from apps.stream.models import StreamId, StreamVariable
from apps.utils.aws.redshift import get_ts_from_redshift
from apps.utils.aws.sns import sns_staff_notification
from apps.utils.data_helpers.manager import DataManager
from apps.utils.gid.convert import int16gid
from apps.utils.timezone_utils import convert_to_utc, formatted_ts, str_to_dt_utc

logger = logging.getLogger(__name__)

WORKER_QUEUE_NAME = getattr(settings, 'SQS_WORKER_QUEUE_NAME')


class StaffOperationsAction(Action):

    @classmethod
    def _arguments_ok(self, args):
        return Action._check_arguments(
            args=args, task_name='StaffOperationsAction',
            required=['operation', 'user', ], optional=['args']
        )

    def _notify_user(self, user, operation, args, notes, op_time):
        email = Email()
        ctx = {
            'user': user.slug,
            'operation': operation,
            'args': args,
            'notes': notes,
            'url': settings.DOMAIN_BASE_URL + '/staff/',
            'op_time': op_time,
        }
        subject = 'IOTile Cloud Staff: Operation completed ({})'.format(operation)
        emails = [user.email, ]
        try:
            email.send_email(label='staff/operation_notification', subject=subject, ctx=ctx, emails=emails)
        except Exception as e:
            logger.warning(str(e))
            raise WorkerActionHardError(
                "Error when sending email. Operation was completed but notification was not sent")

    def _create_devices(self, args, user):
        """Create a batch of devices with a given device_template and sensor graph.
        If an Org is passed, semi-claim this device (assign them to an organization)
        so ArchFX can sync them and we can claim them there.
        num_devices indicates how many devices we should ceate.
        name_format is used as a template to label each device.

        Args:
            args (dict): Required Arguments
            user (Account): User creating devices
        """
        device_template_slug = args['template']
        sg_slug = args['sg']
        org_slug = args['org']

        try:
            device_template = DeviceTemplate.objects.get(slug=device_template_slug)
        except DeviceTemplate.DoesNotExist:
            raise WorkerActionHardError('Device Template not found: {}'.format(device_template_slug))

        try:
            sg = SensorGraph.objects.get(slug=sg_slug)
        except SensorGraph.DoesNotExist:
            raise WorkerActionHardError('SG not found: {}'.format(sg_slug))

        if org_slug:
            try:
                org = Org.objects.get(slug=org_slug)
            except Org.DoesNotExist:
                raise WorkerActionHardError('Org not found: {}'.format(org_slug))
        else:
            org = None

        name_format = args['name_format']
        num_devices = args['num_devices']
        created_devices = []
        for i in range(num_devices):
            device = Device.objects.create(
                template=device_template,
                org=org,
                sg=sg,
                project=None,
                label='temp {0}'.format(i),
                created_by=user
            )
            # Need to modify label after save() to ensure we get ID assigned
            device.label = name_format.format(id=int16gid(device.id))
            device.save()
            created_devices += [device]

        msg = '_create_devices: Successfully created {0} {1} devices.'.format(num_devices, device_template)
        msg += ' First ID={}, Last ID={}'.format(created_devices[0].slug, created_devices[-1].slug)

        return msg

    def _sync_up_permissions(self, args, user):
        """
        Go through all OrgMembership objects, and re-initialize their permissions based on their role
        """
        count = 0
        for membership in OrgMembership.objects.all():
            membership.permissions = ORG_ROLE_PERMISSIONS[membership.role]
            membership.save()
            count += 1

        return '_sync_up_permissions End: Processed {} memberships'.format(count)

    def _sync_up_device_state(self, args, user):
        """
        Go through all Devices and update the state field based on the active field
        """
        count = 0
        for device in Device.objects.all():
            device.state = 'N1' if device.active else 'N0'
            device.save()
            count += 1

        return '_sync_up_device_state End: Processed {} devices'.format(count)

    def _sync_up_e2_event_dates(self, args, user):
        """
        For the given stream, use the StreamData timestamps to update the StreamEventData
        """
        if 'stream' not in args:
            return 'ERROR: Stream not defined'

        try:
            stream = StreamId.objects.get(slug=args['stream'])
        except StreamId.DoesNotExist:
            return 'ERROR: Stream {} does not exist'.format(args['stream'])

        if not (stream.enabled and stream.data_type == 'E2'):
            return 'ERROR: Stream {} not enabled or data_type!=E2'.format(args['stream'])

        data_qs = DataManager.filter_qs(
            'data',
            stream_slug=stream.slug
        )
        event_qs = DataManager.filter_qs(
            'event',
            streamer_local_id__in=[item.int_value for item in data_qs],
            stream_slug=stream.slug
        )
        if data_qs.count() and event_qs.count():
            event_map = {}
            for event in event_qs:
                seq_id = event.incremental_id
                event_map[seq_id] = event

            logger.info('Processing {} events'.format(len(event_map.keys())))

            send_done = False
            with transaction.atomic():
                for data in data_qs:
                    if data.int_value in event_map:
                        # Get event from event map, but also remove so we don't re-process
                        event = event_map.pop(data.int_value)
                        new_timestamp = parse_datetime(formatted_ts(data.timestamp))
                        if event.timestamp != new_timestamp:
                            msg = ""
                            if not send_done:
                                msg += 'event.timestamp={}\n'.format(event.timestamp)
                                msg += 'data.timestamp={}\n'.format(data.timestamp)
                                msg += 'formatted_ts(data.timestamp)={}\n'.format(formatted_ts(data.timestamp))
                                msg += 'get_ts_from_redshift(data.timestamp)= {}\n'.format(
                                    get_ts_from_redshift(data.timestamp))
                                msg += 'convert_to_utc(data.timestamp)={}\n'.format(convert_to_utc(data.timestamp))
                                msg += 'convert_to_utc(data.timestamp).isoformat()={}\n'.format(
                                    convert_to_utc(data.timestamp).isoformat())
                                msg += 'formatted_ts(convert_to_utc(data.timestamp))={}\n'.format(
                                    formatted_ts(convert_to_utc(data.timestamp)))
                                msg += 'str_to_dt_utc(str(data.timestamp))={}\n'.format(
                                    str_to_dt_utc(str(data.timestamp)))
                                msg += 'str_to_dt_utc(formatted_ts(data.timestamp))={}\n'.format(
                                    str_to_dt_utc(formatted_ts(data.timestamp)))
                                msg += 'parse_datetime(formatted_ts(data.timestamp))={}\n'.format(
                                    parse_datetime(formatted_ts(data.timestamp)))

                            event.timestamp = parse_datetime(formatted_ts(data.timestamp))
                            if not send_done:
                                msg += 'event.timestamp (PRE)={}\n'.format(event.timestamp)
                            event.device_timestamp = data.device_timestamp
                            DataManager.save('event', event)
                            if not send_done:
                                msg += 'event.timestamp (POST)={}\n'.format(event.timestamp)
                                sns_staff_notification(msg)
                                send_done = True
        else:
            return 'ERROR: No data (count={}) or events (counts={})'.format(data_qs.count(), event_qs.count())

        return '_sync_up_e2_stream_dates End: Processed {} for {} datas and {} events'.format(
            stream.slug, data_qs.count(), event_qs.count())

    def _sync_up_stream_variable_type(self, args, user):
        """
        Go through streams and update VarTypes for the given Project and Variable.
        Expects args:
        - variable Slug
        """

        if 'variable' not in args:
            return 'ERROR: Variable not defined'

        try:
            var = StreamVariable.objects.get(slug=args['variable'])
        except StreamVariable.DoesNotExist:
            return 'ERROR: Variable {} does not exist'.format(args['variable'])

        var_type = var.var_type

        count = 0
        with transaction.atomic():
            for stream in var.streamids.all():
                logger.info('Updating {} with {}'.format(stream, var_type))
                stream.var_type = var_type
                stream.data_type = var_type.stream_data_type
                stream.is_encoded = var_type.is_encoded

                stream.raw_value_format = var.raw_value_format
                stream.input_unit = var.input_unit
                stream.output_unit = var.output_unit
                stream.save()
                count += 1

        return '_sync_up_stream_var_types End: Processed {} streams'.format(count)

    def _remove_project_from_archive_data_block(self, args, user):
        """
        Go through DataBlock's streams and set the associated project to None.
        This updates streams that where archived previously: streams projects were not set to 0
        Expects args:
        - data_block Slug
        """
        if 'data_block' not in args:
            return 'ERROR: data_block not defined'

        try:
            data_block: DataBlock = DataBlock.objects.get(slug=args['data_block'])
        except DataBlock.DoesNotExist:
            return 'ERROR: DataBlock {} does not exist'.format(args['data_block'])

        logger.info('Processing DataBlock {}'.format(data_block))

        streams = data_block.streamids.all()
        count = 0
        for stream in streams:
            if stream.project is not None or 's--0000-0000' not in stream.slug:
                logger.info('Setting stream {} project to 0'.format(stream))
                old_stream_slug = stream.slug
                assert stream.block == data_block
                stream.project = None
                stream.update_slug_from_parts()
                stream.save()

                # Update StreamData
                data_qs = DataManager.filter_qs('data', stream_slug=old_stream_slug)
                data_qs.update(stream_slug=stream.slug, project_slug='')

                # Update StreamEventData
                event_qs = DataManager.filter_qs('event', stream_slug=old_stream_slug)
                event_qs.update(stream_slug=stream.slug, project_slug='')

                count += 1

        return '_remove_project_from_archive_data_block End: Processed {} streams'.format(count)

    def _bulk_remove_project_from_archive_data_block(self, args, user):
        """
        Go through DataBlocks' streams and set the associated project to None.
        This updates streams that where archived previously: streams projects were not set to 0
        Expects args:
        - data_blocks List[Slug]
        """
        if 'data_blocks' not in args:
            return 'ERROR: data_blocks not defined'

        expected_count = len(args['data_blocks'])

        data_blocks = DataBlock.objects.filter(slug__in=args['data_blocks'])
        count = data_blocks.count()

        if count == 0:
            return 'ERROR: No matching DataBlocks found in database.'

        logger.info('Found {} matching DataBlocks. Beginning process.'.format(count))
        if count < expected_count:
            logger.warning(
                'WARNING: Expected to find {0} data_blocks to process, found actually {1}.'.format(expected_count,
                                                                                                   count))
        for idx, db in enumerate(data_blocks):
            logger.info('Scheduling processing of DataBlock {0} ({1}/{2})'.format(db.slug, idx, count))
            task_payload = {
                "operation": "remove_project_from_archive_data_block",
                "user": user.slug,
                "args": {
                    "data_block": db.slug
                }
            }
            self.schedule(args=task_payload)
            time.sleep(60)

        return '_bulk_remove_project_from_archive_data_block End: Scheduled processing of {0} DataBlocks'.format(count)

    def _unclaim_device(self, args, user):
        """
        Unclaim a device
        """
        # Check for required arguments (will throw an error if required arguments are not present)
        args_ok = Action._check_arguments(
            args=args,
            task_name='UnclaimDeviceAction',
            required=[
                'device',
                'clean_streams',
            ],
            optional=[
                'label'
            ],
        )
        # Get the device
        try:
            device = Device.objects.get(slug=args['device'])
        except Device.DoesNotExist:
            raise WorkerActionHardError("Device with slug {} not found !".format(args['device']))

        clean_streams = args['clean_streams']
        label = args.get('label', f'Device {device.slug}')
        logger.info('Unclaiming device {0}; should clean streams? {1}'.format(device, clean_streams))

        msg = device_unclaim(device=device, label=label, clean_streams=clean_streams)
        logger.info(msg)

    def execute(self, arguments):
        super(StaffOperationsAction, self).execute(arguments)
        if StaffOperationsAction._arguments_ok(arguments):

            operation = arguments['operation']
            user_slug = arguments['user']
            operation_args = arguments.get('args', {})

            user_model = get_user_model()
            try:
                user = user_model.objects.get(slug=user_slug)
            except user_model.DoesNotExist:
                logger.error('User does not exist: {}'.format(user_slug))
                raise WorkerActionHardError('User not found: {}'.format(user_slug))

            if not user.is_staff:
                raise WorkerActionHardError('User {} is not Staff'.format(user_slug))

            factory = {
                'create_devices': self._create_devices,
                'sync_up_permissions': self._sync_up_permissions,
                'sync_up_device_state': self._sync_up_device_state,
                'sync_up_e2_event_dates': self._sync_up_e2_event_dates,
                'sync_up_stream_variable_type': self._sync_up_stream_variable_type,
                'remove_project_from_archive_data_block': self._remove_project_from_archive_data_block,
                'bulk_remove_project_from_archive_data_block': self._bulk_remove_project_from_archive_data_block,
                'unclaim_device': self._unclaim_device,
            }

            start_time = timezone.now()
            if operation in factory:
                msg = factory[operation](operation_args, user)
            else:
                raise WorkerActionHardError('Operation not recognized: {}'.format(operation))
            end_time = timezone.now()

            self._notify_user(
                user=user,
                operation=operation,
                args=operation_args,
                notes=msg,
                op_time=(end_time - start_time)
            )

            logger.info('Processing Operation {}'.format(operation))

    @classmethod
    def schedule(cls, args=None, queue_name=getattr(settings, 'SQS_WORKER_QUEUE_NAME'), delay_seconds=None):
        module_name = cls.__module__
        class_name = cls.__name__
        if StaffOperationsAction._arguments_ok(args):
            super(StaffOperationsAction, cls)._schedule(queue_name, module_name, class_name, args, delay_seconds)
