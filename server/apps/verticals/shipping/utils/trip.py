import logging

from apps.configattribute.models import ConfigAttribute
from apps.datablock.tasks import schedule_archive

logger = logging.getLogger(__name__)


def get_label_by_properties(device, name_type, user):
    """
    Update label for (shipping) device based on config name
    """
    label = device.label
    if not device.label:
        label = 'Device {}'.format(device.slug)

    # Create property map
    properties = list(device.get_properties_qs())
    p_map = {}
    for p in properties:
        p_map[p.name] = p.value

    if not device.sg.ui_extra or not 'web' in device.sg.ui_extra:
        logger.warning('** No uiExtra for {} label={}'.format(device.slug, label))
        return label

    ui_extra = device.sg.ui_extra.get('web')
    # uiExtra will have either `defaultInactiveDeviceName` or `defaultActiveDeviceName`
    if name_type in ui_extra:
        device_default_active_type = ui_extra[name_type]

        # Check to see if there exist a ConfigAttribute
        if 'configAttrSearchName' in device_default_active_type:
            name = device_default_active_type['configAttrSearchName']

            config = ConfigAttribute.objects.get_attribute_by_priority(
                target_slug=device.slug,
                name=name,
                user=user
            )
            if not config:
                return label

            info = config.data

            # We're interested in the label and properties
            if 'properties' in info and 'label' in info:
                label = info.get('label')
                label = label.replace('$slug', device.slug)
                for property_name in info.get('properties'):
                    if property_name in p_map:
                        property_value = p_map[property_name]
                        # Before we can do the replace, we need to remove spaces
                        if property_value:
                            property_name = property_name.replace(' ', '')
                            label = label.replace(property_name, property_value)
        else:
            logger.warning('No configAttrSearchName')

    logger.info('** {}: label final={}'.format(device.slug, label))
    return label


def set_device_to_active(device, user):
    device.set_state('N1')  # state = 'Normal - Active'
    label = get_label_by_properties(device, 'defaultActiveDeviceName', user)
    device.label = label
    device.save()


def on_trip_archive_completed(device, user):
    label = get_label_by_properties(device=device, name_type='defaultInactiveDeviceName', user=user)
    if not label:
        label = 'Device [{}]'.format(device.slug)
    on_complete = {
        'device': {
            'label': label,
            'state': 'N0'
        }
    }
    return on_complete


def schedule_trip_archive(device, block, user):
    """
    Given a fresh data block and associated device, update device label and state,
    and schedule a job for the actual archive.

    :param device: Device that we are archiving
    :param block: DataBlock generated for the device
    :param user: User creating archive
    :return: job PID
    """
    on_complete = on_trip_archive_completed(device, user)

    # Set device to Busy
    device.set_state('B0')
    device.save()

    # Schedule actual archive and store process ID
    # on_complete should be a JSON file representing how to change the device on completion
    pid = schedule_archive(block, on_complete)
    assert pid
    return pid
