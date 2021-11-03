from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from apps.configattribute.models import ConfigAttribute
from apps.org.roles import NO_PERMISSIONS_ROLE

from .models import Org


def get_org_menu_extras(org):
    """
    Check if there are any Config Attributes for extra org related menus in different pages
    :param org: Organization Object
    :return: Object with additional org menus to show. e.g. archive_buttons:
        {
          "url": "/apps/shipping/p--0000-0015/sxd/device/",
          "icon": "fa fa-cloud-upload",
          "label": "SXd Uploader"
        }
    """
    config_name = ':classic:menus:org:extras'
    config_attr = ConfigAttribute.objects.get_attribute(name=config_name, target=org)
    if config_attr:
        return config_attr.data
    return None


class OrgWritePermissionViewMixin(object):
    org = None

    def get(self, *arg, **kwargs):
        if not self.org or not self.org.has_write_access(self.request.user):
            raise PermissionDenied("User has no access to this record")
        return super(OrgWritePermissionViewMixin, self).get(*arg, **kwargs)

    def post(self, *arg, **kwargs):
        if not self.org or not self.org.has_write_access(self.request.user):
            raise PermissionDenied("User has no access to this record")
        return super(OrgWritePermissionViewMixin, self).post(*arg, **kwargs)

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.org = Org.objects.get_from_request(self.request)
        return super(OrgWritePermissionViewMixin, self).dispatch(request, *args, **kwargs)


