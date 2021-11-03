
class DeviceVerticalClaimHelper(object):
    """
    Base Helper class to implement application (verticals)
    specific code during the device claiming process.
    Helper can help configure Orgs and Projects based on
    a given application.
    It also has a function to modify the device itself on
    an application specific way
    """
    _device = None

    def __init__(self, device):
        self._device = device

    def adjust_device(self):
        pass

    def setup_project(self, project):
        pass

    def setup_org(self, org):
        pass
