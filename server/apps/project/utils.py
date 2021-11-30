import logging

from apps.projecttemplate.models import ProjectTemplate
from apps.stream.models import StreamVariable
from apps.utils.gid.convert import gid2int

from .models import Project

logger = logging.getLogger(__name__)


def clone_project(src_project, dst_project_name, description='', dst_org=None, dst_owner=None):
    msg = 'Successfully created new project "{0}"'.format(dst_project_name)

    assert(src_project != None)
    if not dst_org:
        dst_org = src_project.org
    if not dst_owner:
        dst_owner = src_project.created_by

    # 1.- Create new Project
    if (len(dst_project_name) <= 50):
        dst_project = Project.objects.create(
            name=dst_project_name,
            created_by=dst_owner,
            org=dst_org,
            project_template=src_project.project_template,
            is_template=False,
            about=description
        )
    else:
        msg = 'Unable to create new project: Project name too long'
        logger.error(msg)
        return (None, msg)

    # 2.- Copy Stream Variables
    vars = src_project.variables.all()
    count = 0
    for var in vars:
        logger.info('Copying {0}'.format(var.name))
        StreamVariable.objects.create(
            name=var.name,
            about=var.about,
            lid=var.lid,
            units=var.units,
            multiplication_factor=var.multiplication_factor,
            division_factor=var.division_factor,
            offset=var.offset,
            decimal_places=var.decimal_places,
            mdo_label=var.mdo_label,
            var_type=var.var_type,
            input_unit=var.input_unit,
            output_unit=var.output_unit,
            app_only=var.app_only,
            project=dst_project,
            org=dst_org,
            created_by=dst_owner
        )
        count += 1

    if count:
        msg += ' with {0} variables'.format(count)
    msg += '. Use IOTile Companion to claim a device.'

    return (dst_project, msg)


def create_project_from_template(created_by, project_template, project_name, org, description=''):

    assert(project_template != None)

    logger.info('Creating new project from template {0}'.format(project_template))
    master_project = project_template.projects.master_project_for_template(project_template=project_template)
    assert(master_project != None)

    # 1.- Do a normal Clone
    dst_project, msg = clone_project(src_project=master_project,
                                     dst_project_name=project_name,
                                     description=description,
                                     dst_org=org,
                                     dst_owner=created_by)

    return (dst_project, msg)


def create_project_from_device(device, created_by, project_name, org, description=''):
    project = None
    msg = 'Device not properly setup. Contact Arch Support'

    if device and device.sg:
        # 2.- Now add any Variables from the Sensor Graph's variable template set
        sg = device.sg
        if sg:
            project_template = sg.project_template
            project = Project.objects.create(
                name=project_name,
                created_by=created_by,
                org=org,
                is_template=False,
                project_template=project_template,
                about=description
            )
            for obj in sg.variable_templates.all():
                StreamVariable.objects.create_from_variable_template(
                    project=project,
                    var_t=obj,
                    created_by=created_by
                )

    return project, msg


