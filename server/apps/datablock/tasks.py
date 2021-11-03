from django.utils import timezone

from .worker.archive_device_data import ArchiveDeviceDataAction
from .worker.datablock_delete import DataBlockDeleteAction


def schedule_archive(block, on_complete=None):
    if block:
        # 1. Schedule Archiving background task
        args = {
            'data_block_slug': block.slug,
            'on_complete': on_complete
        }
        return ArchiveDeviceDataAction.schedule(args=args)

    return None


def schedule_delete(block, user):
    if block:
        # 1. Schedule delete in background
        return DataBlockDeleteAction.schedule(args={
            'block_slug': block.slug,
            'user': user.slug
        })

    return None
