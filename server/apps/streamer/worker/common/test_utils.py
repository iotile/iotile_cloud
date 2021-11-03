import os
from django.conf import settings

from iotile_cloud.utils.gid import IOTileDeviceSlug, IOTileProjectSlug, IOTileVariableSlug, IOTileStreamSlug

from .types import ENGINE_TYPES

def full_path(filename):
    module_path = os.path.dirname((os.path.dirname(os.path.dirname(__file__))))
    return os.path.join(module_path, 'data', 'reports', filename)


def sqs_process_report_payload(key, ver='v2', ext='.bin'):
    module_name = ENGINE_TYPES[ver][ext]['module_name']
    class_name = ENGINE_TYPES[ver][ext]['class_name']

    return {
        "module": module_name,
        "class": class_name,
        "arguments": {
            "bucket": "dummy_bucket",
            "key": key
        }
    }


def create_test_data(helper, payload, segid):
    results = []
    for item in payload:
        point = helper.build_data_obj(
            stream_slug=item[0],
            device_timestamp=item[1],
            streamer_local_id=segid,
            int_value=item[2]
        )
        segid += 1
        results.append(point)
    return results


def get_reboot_slug(p, d, lid):
    project_slug = IOTileProjectSlug(p.slug)
    device_slug = IOTileDeviceSlug(d.slug)
    variable_slug = IOTileVariableSlug(lid, project=project_slug)
    reboot_slug = IOTileStreamSlug()
    reboot_slug.from_parts(project=project_slug, device=device_slug, variable=variable_slug)
    return str(reboot_slug)


