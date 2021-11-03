"""
This file documents all Org Membership Roles and Permissions.
Permissions are simple traits that restricts views and/or APIs.
Roles represent a collection of permissions.

While the membership record will store the raw permissions, users will only be able
to select within a predefined set of roles.

Current assumptions:
- All users can read Org and Project records, but may not be able to modify them
- All users can read Device records, but may not be able to modify them
- All users can POST notes and device locations, but may not be able to view them
"""


ORG_ROLE_CHOICES = (
    # Arch Staff Roles
    # ----------------
    # Similar to Org Admin, but does not appear on member list
    # NOTE: Most be last to filter out from membership form. See forms.py
    ('s0', 's0 - Arch Support'),

    # Admin Roles
    # -----------
    # Owner is the only user allowed to delete an Organization
    ('a0', 'a0 - Owner'),
    # Admin users have full access to invite/remove members, or make any device management operation
    ('a1', 'a1 - Admin'),

    # Regular Member Roles
    # --------------------
    # Regular members can claim devices, and modify device labels and properties, but cannot create projects
    ('m1', 'm1 - Member'),

    # Restricted Members
    # ------------------
    # Operators are allowed to use the app and upload data, but cannot access the data.
    ('r1', 'r1 - Operator'),

    # Developers
    # ----------
    # Can create variables and streams, and modify device SGs
    # NOTE: Most be last to filter out from membership form. See forms.py
    ('d1', 'd1 - Developer'),
)

# Change the following two constants to define the range of roles that a normal Administrator can change to
MEMBERSHIP_FORM_BEGIN = 1   # Filter Staff Roles
MEMBERSHIP_FORM_END = -1  # Filter Development Roles

# Dictionary of role-name to help with get_role_display() type functionality
ROLE_DISPLAY = dict(ORG_ROLE_CHOICES)

# Default Role for OrgDomains, Invitations, etc.
DEFAULT_ROLE = 'm1'

# See ORG_ROLE_DESCRIPTIONS for documentation on these permissions
ORG_PERMISSIONS = [
    # General Access Permissions
    # --------------------------
    'can_delete_org',
    'can_manage_users',
    'can_manage_ota',
    'can_manage_org_and_projects',
    'can_claim_devices',
    'can_modify_device',
    'can_read_stream_ids',
    'can_modify_stream_ids',
    'can_read_device_properties',
    'can_modify_device_properties',
    'can_read_notes',
    'can_read_device_locations',
    'can_read_stream_data',
    'can_create_stream_data',
    'can_create_datablock',
    'can_access_datablock',
    'can_delete_datablock',
    'can_reset_device',
    'can_access_reports',
    'can_create_reports',
    'can_manage_stream_aliases',

    # Developers
    # ----------
    'can_create_stream_ids',

    # UI Access
    # ---------
    'can_access_classic',
    'can_access_webapp',
    'can_access_companion',
]

ORG_ROLE_DESCRIPTIONS = {
    'can_delete_org': {
        'label': 'Delete Orgs',
        'description': 'User is able to request an Org to be deleted',
        'hidden': False
    },
    'can_manage_users': {
        'label': 'Manage Org Members',
        'description': 'Can Invite and delete members, and change member attributes',
        'hidden': False
    },
    'can_manage_ota': {
        'label': 'Manage OTA',
        'description': 'Can manage Fleets and Over-The-Air (OTA) Deployments',
        'hidden': True
    },
    'can_manage_org_and_projects': {
        'label': 'Manage Org and Projects',
        'description': 'Can modify Org properties, and create, delete and modify Projects (including project properties)',
        'hidden': False
    },
    'can_claim_devices': {
        'label': 'Claim Devices',
        'description': 'Can Claim devices into Org projects',
        'hidden': False
    },
    'can_modify_device': {
        'label': 'Modify Devices',
        'description': 'Can modify device information, including properties, and stream settings',
        'hidden': False
    },
    'can_read_stream_ids': {
        'label': 'Read Streams',
        'description': 'Can read Variables and Stream ID information (Labels, Units, etc)',
        'hidden': False
    },
    'can_modify_stream_ids': {
        'label': 'Modify Streams',
        'description': 'Can modify Stream ID information (Labels, Units, etc), but cannot delete or create',
        'hidden': False
    },
    'can_read_device_properties': {
        'label': 'Read Device Properties',
        'description': 'Can view device properties',
        'hidden': False
    },
    'can_modify_device_properties': {
        'label': 'Modify Device Properties',
        'description': 'Can modify device properties',
        'hidden': False
    },
    'can_read_notes': {
        'label': 'Read Notes',
        'description': 'Can read device or stream notes',
        'hidden': False
    },
    'can_read_device_locations': {
        'label': 'Read Device Locations',
        'description': 'Can access Device GPS locaation history',
        'hidden': False
    },
    'can_create_stream_ids': {
        'label': 'Create Streams',
        'description': 'Can create Variables and Streams',
        'hidden': True
    },
    'can_read_stream_data': {
        'label': 'Read Stream Data',
        'description': 'Can read stream data and events',
        'hidden': False
    },
    'can_create_stream_data': {
        'label': 'Create Stream Data',
        'description': 'Can manually post stream data and events via JSON POST API',
        'hidden': False
    },
    'can_manage_stream_aliases': {
        'label': 'Manage Stream Aliases',
        'description': 'Can create, delete, and modify stream aliases',
        'hidden': False
    },
    'can_create_datablock': {
        'label': 'Archive Device',
        'description': 'Can archive Device data',
        'hidden': False
    },
    'can_access_datablock': {
        'label': 'Access Archived Device',
        'description': 'Can access Archived data',
        'hidden': False
    },
    'can_delete_datablock': {
        'label': 'Delete Archives',
        'description': 'Can delete Archived data',
        'hidden': False
    },
    'can_reset_device': {
        'label': 'Reset Device Data',
        'description': 'Can delete all device data (including trimming data or moving device data), notes and device locations to reset the device to initial state',
        'hidden': False
    },
    'can_access_reports': {
        'label': 'Access Generated Reports',
        'description': 'Can access user generated analytics reports',
        'hidden': False
    },
    'can_create_reports': {
        'label': 'Create Generated Reports',
        'description': 'Can create/schedule user generated analytics reports',
        'hidden': False
    },
    'can_access_classic': {
        'label': 'Access to Classic',
        'description': 'Can access Org pages from the Classic IOTile Cloud (https://iotile.cloud)',
        'hidden': False
    },
    'can_access_webapp': {
        'label': 'Access to WebApp',
        'description': 'Can access Org pages from IOTile Web App (https://app.iotile.cloud)',
        'hidden': False
    },
    'can_access_companion': {
        'label': 'Access Companion',
        'description': 'Can access Org pages from the IOTile Companion mobile app',
        'hidden': False
    },
}


ORG_ROLE_PERMISSIONS = {
    # Staff
    's0': {
        'can_delete_org': True,
        'can_manage_users': True,
        'can_manage_ota': True,
        'can_manage_org_and_projects': True,
        'can_claim_devices': True,
        'can_modify_device': True,
        'can_read_stream_ids': True,
        'can_modify_stream_ids': True,
        'can_read_device_properties': True,
        'can_modify_device_properties': True,
        'can_read_notes': True,
        'can_read_device_locations': True,
        'can_read_stream_data': True,
        'can_create_stream_data': True,
        'can_manage_stream_aliases': True,
        'can_create_datablock': True,
        'can_access_datablock': True,
        'can_delete_datablock': True,
        'can_reset_device': True,
        'can_access_reports': True,
        'can_create_reports': True,
        'can_create_stream_ids': True,
        'can_access_classic': True,
        'can_access_webapp': True,
        'can_access_companion': True,
    },
    # Owner
    'a0': {
        'can_delete_org': True,
        'can_manage_users': True,
        'can_manage_ota': False,
        'can_manage_org_and_projects': True,
        'can_claim_devices': True,
        'can_modify_device': True,
        'can_read_stream_ids': True,
        'can_modify_stream_ids': True,
        'can_read_device_properties': True,
        'can_modify_device_properties': True,
        'can_read_notes': True,
        'can_read_device_locations': True,
        'can_read_stream_data': True,
        'can_create_stream_data': True,
        'can_manage_stream_aliases': True,
        'can_create_datablock': True,
        'can_access_datablock': True,
        'can_delete_datablock': True,
        'can_reset_device': True,
        'can_access_reports': True,
        'can_create_reports': True,
        'can_create_stream_ids': False,
        'can_access_classic': True,
        'can_access_webapp': True,
        'can_access_companion': True,
    },
    # Admin
    'a1': {
        'can_delete_org': False,
        'can_manage_users': True,
        'can_manage_ota': False,
        'can_manage_org_and_projects': True,
        'can_claim_devices': True,
        'can_modify_device': True,
        'can_read_stream_ids': True,
        'can_modify_stream_ids': True,
        'can_read_device_properties': True,
        'can_modify_device_properties': True,
        'can_read_notes': True,
        'can_read_device_locations': True,
        'can_read_stream_data': True,
        'can_create_stream_data': True,
        'can_manage_stream_aliases': True,
        'can_create_datablock': True,
        'can_access_datablock': True,
        'can_delete_datablock': False,
        'can_reset_device': True,
        'can_access_reports': True,
        'can_create_reports': True,
        'can_create_stream_ids': False,
        'can_access_classic': True,
        'can_access_webapp': True,
        'can_access_companion': True,
    },
    # Member
    'm1': {
        'can_delete_org': False,
        'can_manage_users': False,
        'can_manage_ota': False,
        'can_manage_org_and_projects': False,
        'can_claim_devices': False,
        'can_modify_device': True,
        'can_read_stream_ids': True,
        'can_modify_stream_ids': True,
        'can_read_device_properties': True,
        'can_modify_device_properties': True,
        'can_read_notes': True,
        'can_read_device_locations': True,
        'can_read_stream_data': True,
        'can_create_stream_data': True,
        'can_manage_stream_aliases': False,
        'can_create_datablock': False,
        'can_access_datablock': True,
        'can_delete_datablock': False,
        'can_reset_device': False,
        'can_access_reports': True,
        'can_create_reports': False,
        'can_create_stream_ids': False,
        'can_access_classic': False,
        'can_access_webapp': True,
        'can_access_companion': True,
    },
    # Operator
    'r1': {
        'can_delete_org': False,
        'can_manage_users': False,
        'can_manage_ota': False,
        'can_manage_org_and_projects': False,
        'can_claim_devices': False,
        'can_modify_device': False,
        'can_read_stream_ids': True,
        'can_modify_stream_ids': False,
        'can_read_device_properties': False,
        'can_modify_device_properties': False,
        'can_read_notes': False,
        'can_read_device_locations': False,
        'can_read_stream_data': False,
        'can_create_stream_data': True,
        'can_manage_stream_aliases': False,
        'can_create_datablock': False,
        'can_access_datablock': False,
        'can_delete_datablock': False,
        'can_reset_device': False,
        'can_access_reports': False,
        'can_create_reports': False,
        'can_create_stream_ids': False,
        'can_access_classic': False,
        'can_access_webapp': False,
        'can_access_companion': True,
    },
    # Developer
    'd1': {
        'can_delete_org': False,
        'can_manage_users': True,
        'can_manage_ota': True,
        'can_manage_org_and_projects': True,
        'can_claim_devices': True,
        'can_modify_device': True,
        'can_read_stream_ids': True,
        'can_modify_stream_ids': True,
        'can_read_device_properties': True,
        'can_modify_device_properties': True,
        'can_read_notes': True,
        'can_read_device_locations': True,
        'can_read_stream_data': True,
        'can_create_stream_data': True,
        'can_manage_stream_aliases': True,
        'can_create_datablock': True,
        'can_access_datablock': True,
        'can_delete_datablock': False,
        'can_reset_device': True,
        'can_access_reports': True,
        'can_create_reports': True,
        'can_create_stream_ids': True,
        'can_access_classic': True,
        'can_access_webapp': True,
        'can_access_companion': True,
    },
}

# Set No permission role
NO_PERMISSIONS_ROLE = {}
for key in ORG_PERMISSIONS:
    NO_PERMISSIONS_ROLE[key] = False
