
ENGINE_TYPES = {
    'v0': {
        '': {
            'module_name': 'apps.streamer.report.worker.process_report',
            'class_name': 'ProcessReportAction'
        },
        '.bin': {
            'module_name': 'apps.streamer.report.worker.process_report',
            'class_name': 'ProcessReportAction'
        }
    },
    'v1': {
        '': {
            'module_name': 'apps.streamer.worker.v1_bin.process_report',
            'class_name': 'ProcessReportV1Action'
        },
        '.bin': {
            'module_name': 'apps.streamer.worker.v1_bin.process_report',
            'class_name': 'ProcessReportV1Action'
        }
    },
    'v2': {
        '': {
            'module_name': 'apps.streamer.worker.v2_bin.process_report',
            'class_name': 'ProcessReportV2Action'
        },
        '.bin': {
            'module_name': 'apps.streamer.worker.v2_bin.process_report',
            'class_name': 'ProcessReportV2Action'
        },
        '.json': {
            'module_name': 'apps.streamer.worker.v2_json.process_report',
            'class_name': 'ProcessReportV2JsonAction'
        },
        '.mp': {
            'module_name': 'apps.streamer.worker.v2_json.process_report',
            'class_name': 'ProcessReportV2JsonAction'
        }
    },
}

