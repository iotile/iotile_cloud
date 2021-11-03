from django_elasticsearch_dsl import Document, Index, fields

from apps.org.models import Org
from apps.property.models import GenericProperty
from apps.streamnote.models import StreamNote

from .models import Device, DeviceStatus


# Name of the Elasticsearch index
device_index = Index('device')
# See Elasticsearch Indices API reference for available settings


@device_index.doc_type
class DeviceDocument(Document):
    created_by = fields.TextField()
    claimed_by = fields.TextField()
    org = fields.KeywordField()
    sensorgraph = fields.TextField(fields={'raw': fields.KeywordField()})
    slug = fields.TextField(fields={'raw': fields.KeywordField()})
    template = fields.TextField(fields={'raw': fields.KeywordField()})
    notes = fields.TextField()
    properties_val = fields.TextField()
    properties = fields.NestedField(properties={
        'key': fields.KeywordField(),
        'value': fields.TextField(),
        'key_term': fields.KeywordField(),
        'value_term': fields.KeywordField(),
    })

    class Django:
        model = Device

        # The fields of the model to be indexed in Elasticsearch
        fields = [
            'label',
            'created_on'
        ]

        # Ensure the Device will be re-saved when Properties or Notes are updated
        related_models = [GenericProperty, StreamNote]
   
    def prepare_template(self, instance):
        if instance.template:
            return instance.template.slug

    def prepare_org(self, instance):
        if instance.org:
            return instance.org.slug

    def prepare_claimed_by(self, instance):
        if instance.claimed_by:
            return str(instance.claimed_by)
        return ''

    def prepare_created_by(self, instance):
        return str(instance.created_by)

    def prepare_sensorgraph(self, instance):
        if instance.sg:
            return instance.sg.slug
        return ''

    def prepare_properties(self, instance):
        properties = GenericProperty.objects.filter(target=instance.slug)
        return [{
            "key_term": p.name,
            "value_term": p.str_value,
            "key": ''.join(p.name.lower().split()), 
            "value": p.str_value
        } for p in properties]
    
    def prepare_properties_val(self, instance):
        properties = GenericProperty.objects.filter(target=instance.slug)
        return " ".join([ p.str_value for p in properties])

    def prepare_notes(self, instance):
        notes = StreamNote.objects.filter(target_slug=instance.slug)
        return " ".join([n.note for n in notes if n.note])

    def get_instances_from_related(self, related_instance):
        """If related_models is set, define how to retrieve the Device instance(s) from the related model."""
        if isinstance(related_instance, StreamNote) and isinstance(related_instance.target, Device):
            return related_instance.target
        elif isinstance(related_instance, GenericProperty) and isinstance(related_instance.obj, Device):
            return related_instance.obj
