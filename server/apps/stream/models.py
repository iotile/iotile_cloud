import logging
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Manager
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from iotile_cloud.utils.gid import IOTileDeviceSlug, IOTileProjectSlug, IOTileStreamSlug

from apps.datablock.models import DataBlock
from apps.org.models import Org
from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.sensorgraph.models import DisplayWidgetTemplate
from apps.utils.data_helpers.manager import DataManager
from apps.utils.gid.convert import formatted_gvid, gid2int, gid_join, gid_split, int2did, int2pid, int2vid
from apps.vartype.models import VarType, VarTypeInputUnit, VarTypeOutputUnit
from apps.vartype.types import STREAM_DATA_TYPE_CHOICES

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')
logger = logging.getLogger(__name__)

CTYPE_TO_RAW_FORMAT = {
    'int': '<l',
    'unsigned int': '<L',
    'auto': 'auto'
}

# This should equal to data_label max_length in model (100 char)
# but we set it to 50 for now to fit the limit in the mobile app
STREAM_LABEL_MAX_LENGTH = 50


def get_auto_stream_label(device_label, variable_label):
    label = "{} - {}".format(device_label, variable_label)
    label = ('..' + label[-(STREAM_LABEL_MAX_LENGTH - 2):]) if len(label) > STREAM_LABEL_MAX_LENGTH else label
    return label


class StreamVariableManager(Manager):
    """
    Manager to help with Device Management
    """

    def create_variable(self, name, lid, project, created_by, *args, **kwargs):
        org = project.org
        var = self.model(
            name=name,
            lid=lid,
            project=project,
            org=org,
            created_by=created_by
        )
        for key in kwargs:
            assert hasattr(var, key)
            setattr(var, key, kwargs[key])

        var.save()
        return var

    def create_system_variable(self, name, lid, created_by, *args, **kwargs):
        var = self.model(
            name=name,
            lid=lid,
            created_by=created_by
        )
        for key in kwargs:
            assert hasattr(var, key)
            setattr(var, key, kwargs[key])

        var.save()
        return var

    def create_from_variable_template(self, project, var_t, created_by):
        org = project.org
        lid = gid2int(var_t.lid_hex)
        var_type = var_t.var_type
        try:
            variable = self.model.objects.get(project=project, lid=lid)
        except self.model.DoesNotExist as e:
            logger.info(e)
            variable = self.model.objects.create(
                name=var_t.label,
                lid=lid,
                multiplication_factor=var_t.m,
                division_factor=var_t.d,
                offset=var_t.o,
                decimal_places=2,
                var_type=var_type,
                raw_value_format=CTYPE_TO_RAW_FORMAT[var_t.ctype],
                input_unit=var_t.default_input_unit,
                output_unit=var_t.default_output_unit,
                app_only=var_t.app_only,
                web_only=var_t.web_only,
                project=project,
                org=org,
                created_by=created_by
            )

        return variable

    def system_variables_qs(self):
        return self.model.objects.filter(project__isnull=True)

    def user_variables_qs(self, user, project=None):
        orgs = Org.objects.user_orgs_ids(user, permission='can_read_stream_ids')

        if not project:
            return self.model.objects.filter(org__in=orgs)

        return self.model.objects.filter(org__in=orgs, project=project)


class StreamIdManager(Manager):
    """
    Manager to help with Device Management
    """

    def create_stream(self, project, device, variable, created_by, *args, **kwargs):
        if project:
            org = project.org
        else:
            org = device.org

        stream = self.model(
            project=project,
            device=device,
            variable=variable,
            org=org,
            created_by=created_by
        )
        for key in kwargs:
            assert hasattr(stream, key)
            setattr(stream, key, kwargs[key])

        if variable:
            stream.var_lid = variable.lid
            stream.var_name = variable.name
            stream.var_type = variable.var_type

            if 'input_unit' not in kwargs:
                # If not passed, Use the variable's Input Unit
                stream.input_unit = variable.input_unit

            if 'output_unit' not in kwargs:
                # If not passed, Use the variable's Output Unit
                stream.output_unit = variable.output_unit

            if 'multiplication_factor' not in kwargs:
                # If not passed, Use the variable's M
                stream.multiplication_factor = variable.multiplication_factor

            if 'division_factor' not in kwargs:
                # If not passed, Use the variable's D
                stream.division_factor = variable.division_factor

            if 'offset' not in kwargs:
                # If not passed, Use the variable's O
                stream.offset = variable.offset

            if 'raw_value_format' not in kwargs:
                # If not passed, Use the variable's Value Format
                stream.raw_value_format = variable.raw_value_format

        if 'mdo_type' not in kwargs:
            # If not passed, Default to 'UseStream' so the MDO we just set is used
            stream.mdo_type = 'S'

        if 'data_type' not in kwargs:
            # If not passed, Default to basic single value data
            if variable and variable.var_type:
                stream.data_type = variable.var_type.stream_data_type
            else:
                stream.data_type = 'D0'

        if 'data_label' in kwargs:
            stream.data_label = kwargs['data_label']

        stream.save()
        return stream

    def create_stream_by_dev_proj(self, project, device, variable, **kwargs):
        try:
            stream_id = self.model.objects.get(project=project, variable=variable, device=device)
            logger.debug('StreamID already exist. Reusing: {}'.format(stream_id))
        except self.model.DoesNotExist:
            self.create_stream(project=project,
                               variable=variable,
                               device=device,
                               created_by=variable.created_by, **kwargs)

    def create_from_variable_template(self, project, device, var_t, created_by, **kwargs):
        lid = gid2int(var_t.lid_hex)

        try:
            variable = StreamVariable.objects.get(project=project, lid=lid)
        except StreamVariable.DoesNotExist:
            variable = StreamVariable.objects.create_from_variable_template(
                project=project,
                var_t=var_t,
                created_by=created_by
            )

        try:
            stream = StreamId.objects.get(project=project, variable=variable, device=device)
            logger.info('Reusing stream: {}'.format(stream.slug))
        except StreamId.DoesNotExist:
            self.create_stream(project=project,
                               variable=variable,
                               device=device,
                               created_by=created_by, **kwargs)

    def create_after_new_variable(self, var):
        project = var.project
        if project:
            for dev in project.devices.all():
                self.create_stream_by_dev_proj(project=project, device=dev, variable=var)

    def create_after_new_device(self, dev):
        project = dev.project

        if project:
            # If the device has a sensor graph, and the sensor graph has variable templates, use that (New approach)
            # otherwise, create streams of ALL project variables

            # 1.- Create streams for all project variables
            for var in project.variables.all():
                self.create_stream_by_dev_proj(project=project, device=dev, variable=var)

    def get_from_request(self, request):
        resolver_match = request.resolver_match
        if resolver_match:

            if 'stream_id' in resolver_match.kwargs:
                stream_id = resolver_match.kwargs['stream_id']

                return self.model.objects.get(pk=stream_id)

        return None

    def user_streams_qs(self, user, project=None):
        orgs = Org.objects.user_orgs_ids(user, permission='can_read_stream_ids')

        if not project:
            return self.model.objects.filter(org__in=orgs)

        return self.model.objects.filter(org__in=orgs, project=project)

    def clone_into_block(self, src, block):
        """
        Function used to clone a Stream object when archiving a device into a DataBlock
        Everything is copied, except the project is set to zero and the new block is
        also added, resulting in a new Slug.
        For example, if the original slug is s--0000-0010--0000-0000-0000-1234--5001
                     and the new block is 0001, then the new slug is s--0000-0000--0001-0000-0000-1234--5001
        :param src: Original StreamId object
        :param block: DataBlock object
        :return: new StreamID object
        """
        parts = gid_split(src.slug)
        new_slug = block.get_stream_slug_for(parts[3])

        try:
            obj = self.model.objects.get(slug=str(new_slug))
            logger.info('Reusing stream while clonning: {}'.format(obj.slug))
        except self.model.DoesNotExist:
            obj = self.model(
                slug=str(new_slug),
                org=src.org,
                device=src.device,
                block=block,
                input_unit=src.input_unit,
                output_unit=src.output_unit,
                data_label=src.data_label,
                var_lid=src.var_lid,
                var_name=src.var_name,
                var_type=src.var_type,
                multiplication_factor=src.multiplication_factor,
                division_factor=src.division_factor,
                offset=src.offset,
                mdo_type=src.mdo_type,
                mdo_label=src.mdo_label,
                raw_value_format=src.raw_value_format,
                data_type=src.data_type,
                created_by=src.created_by
            )
            obj.save()
        return obj

    def clone_into_another_device(self, src, dst_device):
        """
        Function used to clone a Stream object into another Stream with another Stream Obj
        Everything is copied, except the slug and device
        :param src: Original StreamId object
        :param dst_device: Device to create stream into
        :return: new StreamID object
        """
        var_lid = src.var_lid or src.variable.lid
        new_slug = dst_device.get_stream_slug_for(var_lid)

        obj = self.model(
            slug=new_slug,
            project=dst_device.project,
            variable=src.variable,
            org=dst_device.org,
            device=dst_device,
            input_unit=src.input_unit,
            output_unit=src.output_unit,
            data_label=src.data_label,
            var_lid=src.var_lid,
            var_name=src.var_name,
            var_type=src.var_type,
            multiplication_factor=src.multiplication_factor,
            division_factor=src.division_factor,
            offset=src.offset,
            mdo_type=src.mdo_type,
            mdo_label=src.mdo_label,
            raw_value_format=src.raw_value_format,
            data_type=src.data_type,
            created_by=dst_device.created_by
        )
        obj.save()
        return obj


class StreamVariable(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # variable.name should represent the device port name (i.e. 'IO 1') which should be unique for any
    # given type of device (i.e POD 1 always has IO1 and IO2)
    name = models.CharField(max_length=30)
    about = models.CharField(_('Short Description'), max_length=60, default='', blank=True)
    slug = models.SlugField(max_length=20)

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name='variables', null=True, blank=True)

    # Variables are either project variables (custom variables defined by the sensor graph)
    # or Manufacturer Variables (defined by the device template)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='variables', null=True, blank=True)

    # The local id or lid is the last two bytes of the global stream id, which is
    # generated from the given global device_id and the lid:
    # '0000-0001--0000-0000-0000-0002--0001' where 0001 is the lid
    lid = models.IntegerField(_('Variable ID'), default=0, blank=True)

    var_type = models.ForeignKey(VarType, related_name='variables',
                                 null=True, blank=True, on_delete=models.SET_NULL)
    input_unit = models.ForeignKey(VarTypeInputUnit, related_name='variables',
                                   null=True, blank=True, on_delete=models.SET_NULL)
    output_unit = models.ForeignKey(VarTypeOutputUnit, related_name='variables',
                                    null=True, blank=True, on_delete=models.SET_NULL)

    # If variable is derived, then it re-uses data from another stream
    # Two ways to derived variables:
    # 1.- Derived variable can have its own VarType, in which case, data is computed:
    #               derived_stream(data) * output_unit.mdo
    # 2.- Derived variable has no VarType, in which case, data is computed:
    #               derived_stream(data) * derived_variable.mdo(unit)
    derived_variable = models.ForeignKey('StreamVariable', related_name='derived_variables',
                                         on_delete=models.CASCADE, null=True, blank=True)

    units = models.CharField(max_length=10, default='', blank=True)

    multiplication_factor = models.IntegerField(default=1)
    division_factor = models.IntegerField(default=1)
    offset = models.FloatField(default=0.0)
    decimal_places = models.IntegerField(default=0)
    mdo_label = models.CharField(max_length=10, default='', blank=True)

    # Device values can be encoded in different ways.
    # The following field represents the format of the raw value in each data point
    # We store the format used by the python struct.pack/unpack methods
    # See https://docs.python.org/3.5/library/struct.html#format-characters
    # Defaults to Unsigned Long
    raw_value_format = models.CharField(max_length=5, default='<L', blank=True)

    # Variable only used for IOTile Companion
    app_only = models.BooleanField(default=False, blank=True)
    # Variable only used for Web App
    web_only = models.BooleanField(default=False, blank=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_variables')

    objects = StreamVariableManager()

    class Meta:
        ordering = ['slug']
        unique_together = (('project', 'lid'), )
        verbose_name = _('Stream Variable')
        verbose_name_plural = _('Stream Variables')

    def save(self, *args, **kwargs):
        if self.id:
            # Handle any updates after initial post_save
            if self.project:
                pid = self.project.formatted_gid
            else:
                pid = int2pid(0)

            self.slug = formatted_gvid(pid=pid,
                                       vid=self.formatted_lid)

        super(StreamVariable, self).save(*args, **kwargs)

    def __str__(self):
        return '{0} ({1})'.format(self.slug, self.name)

    @property
    def is_derived(self):
        return self.derived_variable != None

    @property
    def derived_selection(self):
        return self.units

    @property
    def formatted_lid(self):
        return int2vid(self.lid)

    @property
    def formatted_gid(self):
        if self.project:
            pid = self.project.formatted_gid
        else:
            pid = int2pid(0)
        return gid_join([pid, self.formatted_lid, ])

    @property
    def obj_target_slug(self):
        return self.slug

    def set_value_ctype(self, ctype):
        assert ctype in CTYPE_TO_RAW_FORMAT
        self.raw_value_format = CTYPE_TO_RAW_FORMAT[ctype]

    def get_absolute_url(self):
        return reverse('variable:detail', args=(self.slug,))

    def get_edit_url(self):
        return reverse('variable:update', args=(self.slug,))

    def get_units_url(self):
        return reverse('variable:units', args=(self.slug,))

    def get_delete_url(self):
        return reverse('variable:delete', args=(self.slug,))

    def has_access(self, user):
        if user.is_staff:
            return True

        if not self.project:
            # Template variables are accessible by everybody
            return True

        if self.project:
            return self.project.has_access(user)

        return self.created_by == user


class StreamSystemVariable(models.Model):

    variable = models.ForeignKey(StreamVariable, on_delete=models.CASCADE, related_name='system_variables')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='system_variables')

    class Meta:
        ordering = ['project', 'variable']
        unique_together = (('variable', 'project'), )
        verbose_name = _('Stream System Variable')
        verbose_name_plural = _('Stream System Variables')

    def __str__(self):
        return str(self.variable)

    @classmethod
    def project_system_variables(cls, project):
        if project.is_template:
            return StreamSystemVariable.objects.filter(project=project)
        else:
            master_project = Project.objects.filter(project_template_id=project.project_template_id, is_template=True).first()
            if master_project:
                return StreamSystemVariable.objects.filter(project=master_project)
            else:
                logger.warning('Project \'{0}\' has no master project'.format(project))
        return StreamSystemVariable.objects.none()


class StreamId(models.Model):

    MDO_CHOICES = (
        ('V', 'Use Variable: F = Ov + V * Mv/Dv'),
        ('S', 'Use Stream: F = Os + V * Ms/Ds'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    slug = models.SlugField(max_length=42, default='')

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name='streamids', null=True, blank=True)

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='streamids', null=True, blank=True)
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='streamids', null=True, blank=True)
    variable = models.ForeignKey(StreamVariable, related_name='streamids', null=True, blank=True, on_delete=models.SET_NULL)
    block = models.ForeignKey(DataBlock, on_delete=models.CASCADE, related_name='streamids', null=True, blank=True)

    var_lid = models.PositiveIntegerField(_('Variable ID'), default=0, blank=True)
    var_name = models.CharField(max_length=30, default='')
    var_type = models.ForeignKey(VarType, related_name='streamids',
                                 null=True, blank=True, on_delete=models.SET_NULL)
    input_unit = models.ForeignKey(VarTypeInputUnit, related_name='streamids',
                                   null=True, blank=True, on_delete=models.SET_NULL)
    output_unit = models.ForeignKey(VarTypeOutputUnit, related_name='streamids', verbose_name=_('Display units'),
                                    null=True, blank=True, on_delete=models.SET_NULL)

    # This helps us determnte if the stream has an associated StreamData, StreamEvent or both
    data_type = models.CharField(_('Data Type'), max_length=2, choices=STREAM_DATA_TYPE_CHOICES, default='00')

    # The derived stream should be set if the Stream Variable has a derived Variable
    derived_stream = models.ForeignKey('StreamId', on_delete=models.CASCADE,
                                       null=True, blank=True, related_name='derived_streamids')

    # If data_label is '', use variable.name
    data_label = models.CharField(_('Label'), max_length=100, default='', blank=True)

    # Users can overwrite the MDO at the stream level
    # If null, your must use the MDO stored on the StreamVariable, which
    # represents the project wide setting
    multiplication_factor = models.IntegerField(null=True, blank=True)
    division_factor = models.IntegerField(null=True, blank=True)
    offset = models.FloatField(null=True, blank=True)
    mdo_type = models.CharField(_('Factor source'), max_length=2, choices=MDO_CHOICES, default='V')
    mdo_label = models.CharField(max_length=10, default='', blank=True)

    # Cached version of the Variable.raw_value_format
    # Defaults to Unsigned Long
    raw_value_format = models.CharField(max_length=5, default='<L', blank=True)

    # For encoded streams, we will need to access the VarTypeDecoder to understand the encoding
    is_encoded = models.BooleanField(default=False)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_streamids')

    enabled = models.BooleanField(default=True, blank=True)

    objects = StreamIdManager()

    class Meta:
        ordering = ['slug']
        unique_together = (('project', 'device', 'variable', 'block'),)
        verbose_name = _('Stream ID')
        verbose_name_plural = _('Stream IDs')

    def save(self, *args, **kwargs):
        '''
        For now, streamIDs are not reassignable, so we don't want to ever change
        the ID once created. This will allow us to keep the streamId on a given
        project, even if a device is removed or moved to another project
        StreamIDs have to be manually created or removed as needed
        '''
        if self.var_type:
            self.is_encoded = self.var_type.is_encoded
        super(StreamId, self).save(*args, **kwargs)

    def __str__(self):
        return self.slug

    @property
    def formatted_gid(self):
        if self.slug != '':
            # Just remove the 'S--' from the slug
            return self.slug[3:]
        if self.project:
            pid = self.project.formatted_gid
        else:
            pid = int2pid(0)
        if self.block:
            did = self.block.formatted_gid
        elif self.device:
            did = self.device.formatted_gid
        else:
            did = int2did(0)
        assert self.variable
        return gid_join([pid,
                         did,
                         self.variable.formatted_lid, ])

    @property
    def absolute_slug(self):
        if self.derived_stream:
            return self.derived_stream.slug
        else:
            return self.slug

    @property
    def label_or_slug(self):
        if self.data_label and self.data_label != '':
            return self.data_label
        return self.slug

    @property
    def project_ui_label(self):
        if self.data_label and self.data_label != '':
            return self.data_label
        if self.device and self.variable:
            return get_auto_stream_label(self.device.label, self.variable.name)
        return self.slug

    @property
    def obj_target_slug(self):
        return self.slug

    def update_slug_from_parts(self):
        """
        Update the stream slug based on the current project, device, block and variable
        fields.
        This is to be used after a stream project, device or variable is updated
        """
        if self.variable:
            lid = self.variable.lid
        else:
            lid = self.var_lid

        if self.block:
            new_slug = self.block.get_stream_slug_for(lid)
        elif self.device:
            new_slug = self.device.get_stream_slug_for(lid)
        else:
            new_slug = IOTileStreamSlug()
            device_slug = IOTileDeviceSlug(0)
            if self.project:
                proj_slug = IOTileProjectSlug(self.project.slug)
            else:
                proj_slug = IOTileProjectSlug(0)

            new_slug.from_parts(project=proj_slug, device=device_slug, variable=lid)

        self.slug = str(new_slug)

    def get_notes_url(self):
        return reverse('streamnote:list', args=(self.slug,))

    def set_value_ctype(self, ctype):
        assert ctype in CTYPE_TO_RAW_FORMAT
        self.raw_value_format = CTYPE_TO_RAW_FORMAT[ctype]

    def has_access(self, user):
        if user.is_staff:
            return True

        if self.org:
            return self.org.has_access(user)

        return self.created_by == user

    def has_stream_data(self):
        return self.data_type in ['D0', 'E1', 'E2', 'E3']

    def has_stream_event_data(self):
        return self.data_type in ['E0', 'E1', 'E2', 'E3']

    def get_data_count(self):
        stream_id = self.absolute_slug
        count = DataManager.filter_qs('data', stream_slug=stream_id).count()
        return count

    def get_event_count(self):
        stream_id = self.absolute_slug
        count = DataManager.filter_qs('event', stream_slug=stream_id).count()
        return count

    def get_data_qs(self):
        stream_id = self.absolute_slug
        return DataManager.filter_qs('data', stream_slug=stream_id)

    def get_event_qs(self):
        stream_id = self.absolute_slug
        return DataManager.filter_qs('event', stream_slug=stream_id)

    def delete_all_data(self):
        stream_id = self.slug
        DataManager.filter_qs('data', stream_slug=stream_id).delete()
        DataManager.filter_qs('event', stream_slug=stream_id).delete()

    def get_stream_slug_for(self, variable):
        stream_slug = IOTileStreamSlug(self.slug)
        parts = stream_slug.get_parts()
        stream_slug.from_parts(project=parts['project'], device=parts['device'], variable=variable)
        return stream_slug


class DisplayWidgetInstance(models.Model):
    widget = models.ForeignKey(DisplayWidgetTemplate, on_delete=models.CASCADE, related_name='widgetinstances')

    # Either stream or variable should be defined
    stream = models.ForeignKey('StreamId', on_delete=models.CASCADE,
                               related_name='widgetinstances', null=True, blank=True)
    variable = models.ForeignKey('StreamVariable', on_delete=models.CASCADE,
                                 related_name='widgetinstances', null=True, blank=True)

    output_unit = models.ForeignKey(VarTypeOutputUnit, on_delete=models.CASCADE,
                                    related_name='widgetinstances', null=True, blank=True)
    derived_unit_selection = models.CharField(max_length=20, default='', blank=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['id']
        verbose_name = _('Display Widget Instance')
        verbose_name_plural = _('Display Widget Instances')

    def __str__(self):
        return 'DWPI--{0}'.format(self.id)


@receiver(post_save, sender=StreamVariable)
def post_save_variable_callback(sender, **kwargs):
    variable = kwargs['instance']
    created = kwargs['created']
    if created:
        # CRITICAL. Make sure you do not create an infinite loop with the save()
        if variable.project:
            pid = variable.project.formatted_gid
        else:
            pid = int2pid(0)
        variable.slug = formatted_gvid(pid=pid,
                                       vid=variable.formatted_lid)
        variable.save()


@receiver(post_save, sender=StreamId)
def post_save_streamid_callback(sender, **kwargs):
    streamid = kwargs['instance']
    created = kwargs['created']
    if created:
        if streamid.slug and streamid.slug != '':
            # If slug passed, leave as is
            return

        # Update the stream slug based on Project, Block, Device and Variable
        streamid.update_slug_from_parts()
        # CRITICAL. Make sure you do not create an infinite loop with the save()
        streamid.save()


@receiver(pre_delete, sender=StreamId)
def pre_delete_streamid_callback(sender, instance, using, **kwargs):
    streamid = instance
    if streamid:
        logger.debug('Deleting all data for Stream {}'.format(streamid))
        streamid.delete_all_data()


@receiver(pre_delete, sender=StreamVariable)
def pre_delete_streamvariable_callback(sender, instance, using, **kwargs):
    variable = instance
    if variable:
        # Because the model has a on_delete = SET_NULL for the stream to
        # ensure DataBlock streams are not deleted, we need to manually
        # delete active device stream IDs
        streams = variable.streamids.filter(block__isnull=True)
        # DataManager.filter_qs('data', stream_slug__in=[s.slug for s in streams]).delete()
        # DataManager.filter_qs('data', stream_slug__in=[s.slug for s in streams]).delete()
        streams.delete()
