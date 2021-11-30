import logging

from django.conf import settings
from django.db import models
from django.db.models import Manager
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from apps.org.models import Org
from apps.utils.gid.convert import formatted_alias_id, int64gid

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL')
logger = logging.getLogger(__name__)


class StreamAliasManager(Manager):
    """
    Manager to help with Stream Alias Management
    """

    def user_streamalias_qs(self, user):
        orgs = Org.objects.user_orgs_ids(user)
        return StreamAlias.objects.filter(org__in=orgs).select_related('org')


class StreamAlias(models.Model):
    """
    A Stream Alias can be used to dynamically build a virtual stream with sections from different physical streams.
    It is a list of Stream Alias Taps.
    """

    slug = models.SlugField(max_length=24, default='')

    name = models.CharField(max_length=100)
    org = models.ForeignKey(Org, related_name='streamaliases', on_delete=models.CASCADE)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, related_name='created_streamaliases', null=True, blank=True, on_delete=models.SET_NULL)

    objects = StreamAliasManager()

    class Meta:
        ordering = ['slug']
        verbose_name = _('Stream Alias')
        verbose_name_plural = _('Stream Aliases')

    def __str__(self):
        return '{0} - {1}'.format(self.slug, self.name)

    @property
    def formatted_gid(self):
        if self.id:
            return int64gid(self.id)
        return 'UNK'

    def has_access(self, user):
        if user.is_staff:
            return True
        return self.org.has_access(user)


class StreamAliasTapManager(Manager):
    """
    Manager to help with Stream Alias Tap Management
    """

    def user_streamaliastap_qs(self, user):
        aliases = StreamAlias.objects.user_streamalias_qs(user)
        return StreamAliasTap.objects.filter(alias__in=aliases).select_related('alias')


class StreamAliasTap(models.Model):
    """
    A Stream Alias Tap is a timestamped pointer to a physical stream.
    A list of Stream Alias Taps can be used to construct a virtual stream from different data streams.
    """

    alias = models.ForeignKey(StreamAlias, related_name='taps', on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    stream = models.ForeignKey('stream.StreamId', related_name='streamaliastaps', on_delete=models.CASCADE)

    created_on = models.DateTimeField('created_on', auto_now_add=True)
    created_by = models.ForeignKey(AUTH_USER_MODEL, related_name='created_streamaliastaps', null=True, blank=True, on_delete=models.SET_NULL)

    objects = StreamAliasTapManager()

    class Meta:
        ordering = ['id']
        verbose_name = _('Stream Alias Tap')
        verbose_name_plural = _('Stream Alias Taps')

    def __str__(self):
        return 'Stream Alias Tap {}'.format(self.id)

    def has_access(self, user):
        if user.is_staff:
            return True

        return self.alias.has_access(user)


@receiver(post_save, sender=StreamAlias)
def post_save_streamalias_callback(sender, **kwargs):
    stream_alias = kwargs['instance']
    created = kwargs['created']
    if created:
        # CRITICAL. Make sure you do not create an infinite loop with the save()
        stream_alias.slug = formatted_alias_id(stream_alias.formatted_gid)
        stream_alias.save()
