from django_elasticsearch_dsl import Document, Index, fields

from apps.org.models import Org
from apps.property.models import GenericProperty
from apps.streamnote.models import StreamNote

from .models import DataBlock

# Name of the Elasticsearch index
datablock_index = Index('datablock')
# See Elasticsearch Indices API reference for available settings
datablock_index.settings(
    number_of_shards=1,
    number_of_replicas=0
)


@datablock_index.doc_type
class DataBlockDocument(Document):
    created_by = fields.TextField()    
    org = fields.KeywordField()
    sensorgraph = fields.TextField(fields={'raw': fields.KeywordField()})
    slug = fields.TextField(fields={'raw': fields.KeywordField()})
    title = fields.TextField()
    notes = fields.TextField()
    properties_val = fields.TextField()
    properties = fields.NestedField(properties={
        'key': fields.KeywordField(),
        'value': fields.TextField(),
        'key_term': fields.KeywordField(),
        'value_term': fields.KeywordField(),
    })

    class Django:
        model = DataBlock

        # The fields of the model you want to be indexed in Elasticsearch
        fields = [
            'description',
            'created_on'
        ]
        # Ensure the DataBlock will be re-saved when Properties or Notes are updated
        related_models = [GenericProperty, StreamNote]

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

    def prepare_created_by(self, instance):
        return instance.created_by.name

    def prepare_org(self, instance):
        if instance.org:
            return str(instance.org.slug)

    def prepare_sensorgraph(self, instance):
        if instance.sg:
            return instance.sg.slug
        return ''

    def prepare_notes(self, instance):
        notes = StreamNote.objects.filter(target_slug=instance.slug)
        return " ".join([n.note for n in notes if n.note])

    def get_instances_from_related(self, related_instance):
        """If related_models is set, define how to retrieve the DataBlock instance(s) from the related model."""
        if isinstance(related_instance, StreamNote) and isinstance(related_instance.target, DataBlock):
            return related_instance.target
        elif isinstance(related_instance, GenericProperty) and isinstance(related_instance.obj, DataBlock):
            return related_instance.obj