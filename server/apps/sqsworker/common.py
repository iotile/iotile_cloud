import json

ACTION_CLASS_MODULE = {
    'ProcessReportAction': {
        'module': 'apps.streamer.report.worker.process_report',
        'class': 'ProcessReportAction',
        'label': 'Process Report (V0 Bin)',
    },
    'ProcessReportV1Action': {
        'module': 'apps.streamer.worker.v1_bin.process_report',
        'class': 'ProcessReportV1Action',
        'label': 'Process Report (V1 Bin)',
    },
    'ProcessReportV2Action': {
        'module': 'apps.streamer.worker.v2_bin.process_report',
        'class': 'ProcessReportV2Action',
        'label': 'Process Report (V2 Bin)',
    },
    'ReProcessDataV2Action': {
        'module': 'apps.streamer.worker.v2_bin.reprocess_data',
        'class': 'ReProcessDataV2Action',
        'label': 'Re-Process Report (V2 Bin)',
    },
    'ReProcessOneRebootV2Action': {
        'module': 'apps.streamer.worker.v2_bin.reprocess_one_reboot',
        'class': 'ReProcessOneRebootV2Action',
        'label': 'Re-Process One Reboot (V2)',
    },
    'HandleChoppedReportV2Action': {
        'module': 'apps.streamer.worker.v2_bin.handle_chopped_report',
        'class': 'HandleChoppedReportV2Action',
        'label': 'Handle Chopped Report (V2 Bin)',
    },
    'ProcessReportV2JsonAction': {
        'module': 'apps.streamer.worker.v2_json.process_report',
        'class': 'ProcessReportV2JsonAction',
        'label': 'Process Report (V2 Json/msgPk)',
    },
    'SyncUpE2DataAction': {
        'module': 'apps.streamer.worker.v2_json.syncup_e2_data',
        'class': 'SyncUpE2DataAction',
        'label': 'Sync Up event timestamps (E2)',
    },
    'AdjustTimestampAction': {
        'module': 'apps.streamer.worker.misc.adjust_timestamp',
        'class': 'AdjustTimestampAction',
        'label': 'Adjust timestamps of data or event given a base_ts',
    },
    'AdjustTimestampReverseV2Action': {
        'module': 'apps.streamer.worker.misc.adjust_timestamp_reverse',
        'class': 'AdjustTimestampReverseV2Action',
        'label': 'Auto Adjust timestamps of data or event from last item',
    },
    'ReprocessDeviceEventDataAction': {
        'module': 'apps.streamevent.worker.reprocess_event_data',
        'class': 'ReprocessDeviceEventDataAction',
        'label': 'Re-Process Device Event Data (E1)',
    },
    'HandleRebootAction': {
        'module': 'apps.streamer.report.worker.handle_reboot',
        'class': 'HandleRebootAction',
        'label': 'Handle Reboot',
    },
    'HandleDelayAction': {
        'module': 'apps.streamer.report.worker.handle_delay',
        'class': 'HandleDelayAction',
        'label': 'Handle Delay',
    },
    'PingAction': {
        'module': 'apps.sqsworker.worker',
        'class': 'PingAction',
        'label': 'Ping Worker',
    },
    'WorkerShutDownAction': {
        'module': 'apps.sqsworker.worker',
        'class': 'WorkerShutDownAction',
        'label': 'Shut Down ONE Worker',
    },
    'WorkerHealthCheckAction': {
        'module': 'apps.sqsworker.worker',
        'class': 'WorkerHealthCheckAction',
        'label': 'Worker Health Check',
    },
    'DbStatsAction': {
        'module': 'apps.staff.worker.dbstats',
        'class': 'DbStatsAction',
        'label': 'Compute DB Stats',
    },
    'RemoveDuplicateAction': {
        'module': 'apps.staff.worker.remove_duplicate',
        'class': 'RemoveDuplicateAction',
        'label': 'Remove Stream Data duplicates',
    },
    'HealthCheckStreamDataAction': {
        'module': 'apps.staff.worker.healthcheck_stream_data',
        'class': 'HealthCheckStreamDataAction',
        'label': 'Check Stream Data Health',
    },
    'WorkerCollectStatsAction': {
        'module': 'apps.sqsworker.worker',
        'class': 'WorkerCollectStatsAction',
        'label': 'Worker Collect Stats',
    },
    'UpdateEventExtraDataAction': {
        'module': 'apps.streamevent.worker.update_event_extra_data',
        'class': 'UpdateEventExtraDataAction',
        'label': 'Update Event Extra Data',
    },
    'DeviceDataResetAction': {
        'module': 'apps.physicaldevice.worker.device_data_reset',
        'class': 'DeviceDataResetAction',
        'label': 'Reset Device Data',
    },
    'DeviceDataTrimAction': {
        'module': 'apps.physicaldevice.worker.device_data_trim',
        'class': 'DeviceDataTrimAction',
        'label': 'Trim Device Data',
    },
    'DeviceMoveAction': {
        'module': 'apps.physicaldevice.worker.device_move',
        'class': 'DeviceMoveAction',
        'label': 'Device Move',
    },
    'DeviceUnClaimAction': {
        'module': 'apps.physicaldevice.worker.device_unclaim',
        'class': 'DeviceUnClaimAction',
        'label': 'Unclaim Device',
    },
    'ArchiveDeviceDataAction': {
        'module': 'apps.datablock.worker.archive_device_data',
        'class': 'ArchiveDeviceDataAction',
        'label': 'Archive Device Data',
    },
    'DataBlockDeleteAction': {
        'module': 'apps.datablock.worker.datablock_delete',
        'class': 'DataBlockDeleteAction',
        'label': 'Delete DataBlock',
    },
    'ReportGeneratorAction': {
        'module': 'apps.report.worker.report_generator',
        'class': 'ReportGeneratorAction',
        'label': 'Generate User Reports',
    },
    'DeviceStatusCheckAction': {
        'module': 'apps.physicaldevice.worker.device_status_check',
        'class': 'DeviceStatusCheckAction',
        'label': 'Check Device Status',
    },
    'MoveDeviceStreamDataAction': {
        'module': 'apps.staff.worker.move_device_stream_data',
        'class': 'MoveDeviceStreamDataAction',
        'label': 'Staff: Move Device Stream Data to another device',
    },
    'StaffOperationsAction': {
        'module': 'apps.staff.worker.staff_operations',
        'class': 'StaffOperationsAction',
        'label': 'Staff: Execute Staff Operation',
    },
    'ProjectDeleteAction': {
        'module': 'apps.project.worker.delete_project',
        'class': 'ProjectDeleteAction',
        'label': 'Delete Project',
    },
    'OrgSendMessageAction': {
        'module': 'apps.org.worker.message_members',
        'class': 'OrgSendMessageAction',
        'label': 'Send messages to Org Members',
    },
    'ForwardStreamerReportAction': {
        'module': 'apps.streamer.worker.misc.forward_streamer_report',
        'class': 'ForwardStreamerReportAction',
        'label': 'Forward Strreamer Report to ArchFx',
    },
}

ACTION_LIST = [k for k in ACTION_CLASS_MODULE.keys()] + ['WorkerStarted', ]
ACTION_CHOICES = [(k, ACTION_CLASS_MODULE[k]['label']) for k in ACTION_CLASS_MODULE.keys()]
