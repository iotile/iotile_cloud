from django.urls import reverse

from apps.configattribute.models import get_or_create_config_name

from .helpers.analytics_report_availability_helper import AnalyticsReportAvailabilityHelpter
from .helpers.device_claim_helper import DeviceVerticalClaimHelper
from .shipping.utils.analytics_report_availability import ShippingAnalyticsReportAvailabilityHelpter
from .shipping.utils.device_claim_helper import ShippingDeviceVerticalClaimHelper
from .shipping.utils.project_status_report import TripProjectStatusReport
from .shipping.utils.trip import on_trip_archive_completed


def _is_shipping_device(obj):
    """True if device is used as a shipping tracker"""
    if obj and obj.sg:
        return ('shipping' in obj.sg.slug.split('-')) or ('saver' in obj.sg.slug.split('-'))
    return False


def _is_shipping_project(project):
    """True if project contains shipping tracker devices"""
    pt = project.project_template
    return pt and 'Shipping' in pt.name


def get_data_block_vertical_helper(block):
    """
    Return appropriate DataBlockCreateVerticalHelper
    based on the type of data block

    :param block: DataBlock
    :return: derived DataBlockCreateVerticalHelper object
    """

    # For now, always return base class
    return DataBlockCreateVerticalHelper(block)


def get_device_detail_vertical_helper(device):
    """
    Return appropriate DeviceDetailVerticalActions
    based on the type of device

    :param device: Physical Device
    :return: derived DeviceDetailVerticalActions object
    """

    # For now, always return base class
    return DeviceDetailVerticalActions(device)


def get_device_claim_vertical_helper(device):
    """
    Return appropriate DeviceVerticalClaimHelper
    based on the type of device

    :param device: Physical Device
    :return: derived DeviceVerticalClaimHelper object
    """

    # For now, always return base class
    if _is_shipping_device(device):
        return ShippingDeviceVerticalClaimHelper(device)

    return DeviceVerticalClaimHelper(device)


def get_analytics_report_availability_vertical_helper(device_or_block):
    """
    Return appropriate AnalyticsReportAvailabilityHelpter
    based on the type of device or block

    :param device_or_block: Physical Device or Data Block
    :return: derived AnalyticsReportAvailabilityHelpter object
    """

    # For now, always return base class
    if _is_shipping_device(device_or_block):
        return ShippingAnalyticsReportAvailabilityHelpter(device_or_block)

    return AnalyticsReportAvailabilityHelpter(device_or_block)


class DataBlockCreateVerticalHelper(object):
    """
    Helper class to help do application (vertical) specific archiving
    """
    _block = None

    def __init__(self, block):
        self._block = block

    def on_complete(self, user):
        """
        Return dict with instructions for what the archiver worker should done on_complete

        :param user: User creting archive
        :return: on_complete dict with 'label' and 'state' defined
        """
        device = self._block.device

        # If shipping device, end the trip first
        if _is_shipping_device(device):
            return  on_trip_archive_completed(device, user)

        return {}


class DeviceDetailVerticalActions(object):
    """
    Helper class to add application (verticals) specific buttons
    items to the User Device Page's Actions Section
    """
    _device = None

    def __init__(self, device):
        self._device = device

    def action_menus(self, user):
        org = self._device.org
        if not org:
            return []
        menus = []
        if _is_shipping_device(self._device):
            if self._device.state == 'N0': # Inactive
                if org.has_permission(user, 'can_modify_device_properties'):
                    menus.append({
                        'url': reverse('apps-shipping:start-trip', args=(self._device.slug,)),
                        'label': 'Trip setup',
                    })
            if self._device.state == 'N1': # Active
                if org.has_permission(user, 'can_create_datablock'):
                    menus.append({
                        'url': self._device.get_create_archive_url(),
                        'label': 'End Trip and Archive',
                    })
        else:
            if org.has_permission(user, 'can_create_datablock'):
                menus.append({
                    'url': self._device.get_create_archive_url(),
                    'label': 'Archive Device Data',
                })

        return menus


class ProjectDetailViewHelper(object):

    @staticmethod
    def get_vertical_context_data(project):
        if _is_shipping_project(project):
            context = {}
            summary = TripProjectStatusReport(project)
            summary.analyze()
            context['config'] = summary.config
            context['results'] = summary.results
            context['device_count'] = summary.device_count
            context['active_count'] = summary.active_count
            context['ended_count'] = summary.ended_count
            # Build device array for locations to work
            context['devices'] = [item.device for key, item in context['results'].items()]

            return context

        return None

    @staticmethod
    def get_template_names(project):
        if _is_shipping_project(project):
            return 'shipping/project-status.html'

        return None
