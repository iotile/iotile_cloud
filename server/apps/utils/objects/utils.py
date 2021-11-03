import logging
from django.apps import apps

from iotile_cloud.utils.gid import IOTileBlockSlug
from apps.utils.aws.sns import sns_staff_notification

logger = logging.getLogger(__name__)


def _get_model_for(type):
    name = model = None
    _model_factory = {
        '@': ('user', apps.get_model('authentication', 'Account')),
        '^': ('org', apps.get_model('org', 'Org')),
        'b': ('datablock', apps.get_model('datablock', 'DataBlock')),
        'd': ('device', apps.get_model('physicaldevice', 'Device')),
        'p': ('project', apps.get_model('project', 'Project')),
        's': ('stream', apps.get_model('stream', 'StreamId')),
        'a': ('streamalias', apps.get_model('streamalias', 'StreamAlias')),
        'v': ('variable', apps.get_model('stream', 'StreamVariable')),
        'g': ('fleet', apps.get_model('fleet', 'Fleet')),
    }
    if type in _model_factory:
        name, model = _model_factory[type]

    return name, model


def _get_real_slug(slug):
    _slug_factory = {
        '@': lambda slug: slug[1:],
        '^': lambda slug: slug[1:],
    }
    if slug[0] in _slug_factory:
        return _slug_factory[slug[0]](slug)
    return slug


def get_object_by_slug(slug):
    """
    Get an object from the database given a slug. e.g.
    A slug with 'd--' will return a Device, while a slug with 's--' returns a Stream

    :param slug: Any slug
    :return: A (<name>, <obj>) tuple, assuming the slug is correct and the object exist.
    If the slug is correct, but the object does not exist, (<name>, None) is returned
    """
    name, model = _get_model_for(slug[0])

    if name and model:
        try:
            obj = model.objects.get(slug=_get_real_slug(slug))
            return name, obj
        except model.MultipleObjectsReturned as e:
            # This is wrong as there should never be a duplicate
            # for lets not crash if we do:
            # https://github.com/iotile/QA/issues/94
            msg = 'get_object_by_slug({}): Found duplicated slug - {}'.format(slug, e)
            logger.warning(msg)
            sns_staff_notification(msg)
            obj_list = model.objects.filter(slug=_get_real_slug(slug))
            return name, obj_list.first()
        except model.DoesNotExist:
            return name, None
    return None, None


def get_device_or_block(slug):
    """
    Function to get a Device or DataBlock based on the slug
    :param slug: slug starting with 'b--' or 'd--'
    :return: Device or DataBlock or None
    """
    try:
        block_slug = IOTileBlockSlug(slug)
    except Exception:
        return None

    if block_slug.get_block() > 0:
        name, model = _get_model_for('b')
    else:
        name, model = _get_model_for('d')

    try:
        obj = model.objects.get(slug=slug)
        return obj
    except model.DoesNotExist:
        return None
