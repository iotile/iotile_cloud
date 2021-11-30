import logging
import uuid

from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.db.models import Manager
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.stream.models import StreamId, StreamVariable
from apps.utils.gid.convert import formatted_gfid
from apps.vartype.models import VarTypeOutputUnit

from .actions.types import *
from .processing.trigger import evaluate_trigger

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')
logger = logging.getLogger(__name__)


def delete_serialized_filter_cache_for_slug(slug):
    if cache:
        logger.debug('StreamFilter: cache(DELETE)={0}'.format(slug))
        cache.delete(slug)


class StreamFilterManager(Manager):
    """
    Manager to help with Device Management
    """

    def _create_filter(self, proj, var, created_by, *args, **kwargs):
        obj = self.model(
            project=proj,
            variable=var,
            created_by=created_by
        )
        for key in kwargs:
            assert(hasattr(obj, key))
            setattr(obj, key, kwargs[key])

        obj.save()
        return obj

    def create_filter_from_device_and_variable(self, dev, var, created_by, *args, **kwargs):
        assert (dev.project_id == var.project_id)
        proj = dev.project
        try:
            stream = StreamId.objects.get(project=proj, device=dev, variable=var)
            obj = self._create_filter(device=dev, input_stream=stream, var=var, proj=proj,
                                      created_by=created_by, *args, **kwargs)
        except StreamId.DoesNotExist:
            logger.warning('StreamId not found for p={0}, d={1}, v={2}'.format(proj, dev, var))
            return None

        return obj

    def create_filter_from_project_and_variable(self, proj, var, created_by, *args, **kwargs):
        assert (proj.id == var.project_id)
        obj = self._create_filter(device=None, input_stream=None, var=var, proj=proj,
                                  created_by=created_by, *args, **kwargs)

        return obj

    def create_filter_from_streamid(self, input_stream, created_by, *args, **kwargs):
        proj = input_stream.project
        if input_stream.device:
            dev = input_stream.device
        else:
            dev = None
        var = input_stream.variable
        obj = self._create_filter(device=dev, input_stream=input_stream, var=var, proj=proj,
                                  created_by=created_by, *args, **kwargs)

        return obj

    def user_stream_filter_qs(self, user, project=None):
        if not project:
            projects = Project.objects.user_project_qs(user)
            qs = self.model.objects.filter(project__in=projects, active=True)
        else:
            qs = self.model.objects.filter(project=project, active=True)
        return qs.select_related('project')

    def project_stream_filter_qs(self, project=None):
        return self.model.objects.filter(project=project, active=True)


class StreamFilter(models.Model):
    """
    ** DESCRIPTION **
    Stream Filters are intended to represent a processing task that should be done
    on every Stream Data coming in from a device.
    Any given stream should only have TWO potential filters associated to it, but
    only one (based on the following priority) is ever executed:
    1.- StreamFilters with an associated stream_input:
           f--0000-0001--0000-0000-0000-0002--0003: Stream 1 from Device 2 in Project 3
    2.- StreamFilters without an associated stream_input, which represent
        "for all devices in project for a given variable" (a wildcard):
           f--0000-0001----0003: Stream 1 from ANY device in Project 3
    """

    name = models.CharField(max_length=50, default='')

    # The slug represents a globally unique ID that tells which streams
    # should be processed. Slugs format is:
    #   f--<projectID>--<deviceID>--<variableID> (Same format as a StreamID, but with an "f")
    # A deviceID='' represents a project wide filter (basically a wildcard)
    slug = models.SlugField(max_length=48, unique=True)

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='stream_filters')
    variable = models.ForeignKey(StreamVariable, on_delete=models.CASCADE, related_name='stream_filters')
    # If device is null, it represents a wildcard: All devices within project
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='stream_filters', null=True, blank=True)

    # This is redundant in that project--device--variable gives you a stream, but this makes
    # it easy to go from stream to filter and viceversa. It is optional for the case when
    # we have a project-wide filter
    # TODO: Consider if we should instead automatically ALWAYS create project streams
    # TODO: Or if we should instead have the concept of a Project-wide StreamId
    input_stream = models.OneToOneField('stream.StreamId', on_delete=models.CASCADE,
                                        related_name='stream_filter', null=True, blank=True)

    active = models.BooleanField(default=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    objects = StreamFilterManager()

    class Meta:
        ordering = ['slug']
        verbose_name = _("Stream Filter")
        verbose_name_plural = _("Stream Filters")

    def __str__(self):
        if self.slug:
            return self.slug
        return self.name

    def save(self, *args, **kwargs):
        if not self.project and self.input_stream:
            self.project = self.input_stream.project
        if not self.project and self.device and self.device.project:
            self.project = self.device.project

        if self.input_stream:
            elements = self.input_stream.slug.split('--')
            self.slug = '--'.join(['f', ] + elements[1:])
        elif self.project:
            if self.device:
                did = self.device.formatted_gid
            else:
                # If no device, this is a project-wide filter. Use 0000-0000-0000-0000 as device
                did = None

            self.slug = formatted_gfid(pid=self.project.formatted_gid,
                                       did=did,
                                       vid=self.variable.formatted_lid)

        super(StreamFilter, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('filter:detail', kwargs={'slug': self.slug})

    def has_access(self, user):
        if user.is_staff:
            return True

        if self.project:
            return self.project.has_access(user)

        return self.created_by == user


class StreamFilterAction(models.Model):

    on = models.CharField(max_length=5, choices=FILTER_ACTION_ON_CHOICES, default='entry')
    type = models.CharField(max_length=5, choices=FILTER_ACTION_TYPE_CHOICES)

    state = models.ForeignKey('State', on_delete=models.CASCADE, related_name='actions', null=True, blank=True)

    # for notification email, extra_payload contains notification_recipient and notification_level
    extra_payload = models.JSONField(null=True, blank=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['id']
        verbose_name = _("Stream Filter Action")
        verbose_name_plural = _("Stream Filter Actions")

    def __str__(self):
        action_str = 'Action {0} ({1}). On {2} state {3}'.format(self.id, self.type, self.on, self.state_id)
        return action_str

    def save(self, *args, **kwargs):
        super(StreamFilterAction, self).save(*args, **kwargs)


class State(models.Model):
    label = models.CharField(max_length=50, default='')
    slug = models.SlugField(max_length=50)
    filter = models.ForeignKey(StreamFilter, on_delete=models.CASCADE, related_name='states', null=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['filter', 'slug']
        verbose_name = _("Filter State")
        verbose_name_plural = _("Filter States")
        unique_together = (('filter', 'slug'),)

    def save(self, *args, **kwargs):
        self.slug = slugify(self.label)
        super(State, self).save(*args, **kwargs)

    def __str__(self):
        return self.label

    @property
    def entry_action_qs(self):
        return self.actions.filter(on='entry')

    @property
    def exit_action_qs(self):
        return self.actions.filter(on='exit')



class StateTransition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    filter = models.ForeignKey(StreamFilter, on_delete=models.CASCADE, related_name='transitions', null=True)
    src = models.ForeignKey(State, on_delete=models.CASCADE, related_name='out_transitions', null=True, blank=True)
    dst = models.ForeignKey(State, on_delete=models.CASCADE, related_name='in_transitions', null=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['src', 'dst']
        verbose_name = _("State Transition")
        verbose_name_plural = _("State Transitions")
        unique_together = (('filter', 'src', 'dst'),)

    def __str__(self):
        src_label = self.src.label if self.src else '*'
        return "{}: {} -> {}".format(self.filter.slug, src_label, self.dst.label)


class StreamFilterTrigger(models.Model):

    OPERATOR_CHOICES = (
        ('bu', 'Buffer (no-op)'),
        ('eq', 'Equal (==)'),
        ('ne', 'Not Equal (!=)'),
        ('le', 'Less or equal than (<=)'),
        ('ge', 'Greater or equal than (>=)'),
        ('lt', 'Less than (<)'),
        ('gt', 'Greater than (>)'),
    )

    operator = models.CharField(max_length=2, choices=OPERATOR_CHOICES)
    threshold = models.FloatField(null=True, blank=True)

    # Value of threshold entered by user
    user_threshold = models.FloatField(blank=True, null=True)
    # unit of user_threshold
    user_output_unit = models.ForeignKey(VarTypeOutputUnit, related_name='output_unit',
                                         null=True, blank=True, on_delete=models.SET_NULL)

    filter = models.ForeignKey(StreamFilter, on_delete=models.CASCADE, related_name='triggers')

    transition = models.ForeignKey(StateTransition, on_delete=models.CASCADE,
                                   related_name="triggers", null=True, blank=True)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['id']
        verbose_name = _("Stream Filter Trigger")
        verbose_name_plural = _("Stream Filter Triggers")

    def __str__(self):
        return '{0} - {1} {2}'.format(self.id, self.operator, self.threshold)

    @property
    def user_unit_full(self):
        if self.user_output_unit:
            return self.user_output_unit.unit_full
        return None

    def evaluate(self, value):
        trigger = {
            'operator': self.operator,
            'threshold': self.threshold
        }
        return evaluate_trigger(trigger, value)


@receiver(post_save, sender=StreamFilter)
def post_save_streamfilter_callback(sender, **kwargs):
    stream = kwargs['instance']
    logger.debug('post-save: {0}'.format(stream.slug))
    delete_serialized_filter_cache_for_slug(stream.slug)


@receiver(pre_delete, sender=StreamFilter)
def pre_delete_streamfilter_callback(sender, **kwargs):
    stream = kwargs['instance']
    logger.debug('pre-delete: {0}'.format(stream.slug))
    delete_serialized_filter_cache_for_slug(stream.slug)

@receiver(post_save, sender=State)
def post_save_state_callback(sender, **kwargs):
    state = kwargs['instance']
    logger.debug('post-save-state: {0}'.format(state.filter.slug))
    delete_serialized_filter_cache_for_slug(state.filter.slug)

@receiver(post_save, sender=StateTransition)
def post_save_state_transition_callback(sender, **kwargs):
    transition = kwargs['instance']
    logger.debug('post-save-state: {0}'.format(transition.filter.slug))
    delete_serialized_filter_cache_for_slug(transition.filter.slug)
