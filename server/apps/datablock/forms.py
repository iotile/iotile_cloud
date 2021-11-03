from django.forms import ModelForm
from django import forms

# from haystack.forms import SearchForm

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, HTML
from crispy_forms.bootstrap import FieldWithButtons

from apps.utils.data_mask.form_mixins import DataMaskFormMixin, DATETIME_WIDGET_OPTIONS
from apps.utils.data_mask.mask_utils import get_data_mask_date_range
from apps.utils.timezone_utils import str_to_dt_utc

from .models import *
from .documents import DataBlockDocument


class DataBlockBasicUpdateForm(ModelForm):
    class Meta:
        model = DataBlock
        fields = ['title', 'description']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))

        super(DataBlockBasicUpdateForm, self).__init__(*args, **kwargs)


class DataBlockCreateForm(ModelForm):
    class Meta:
        model = DataBlock
        fields = ['title', 'description']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        note = """
        <div class="alert alert-success alert-dismissible fade in" role="alert">
        This operation will move all device stream data and device properties
        to a new device data block (archive) and will then reset  the device.
        </div>
        """
        self.helper.layout = Layout(
            HTML(note),
            'title',
            'description',
            HTML('<br>'),
        )

        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))

        super(DataBlockCreateForm, self).__init__(*args, **kwargs)


class DataBlockSearchForm(forms.Form):
    q = forms.CharField(required=False, label=('Search'),
                        widget=forms.TextInput(attrs={'type': 'search'}))
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'get'
        self.helper.layout = Layout(
            FieldWithButtons('q', Submit('search', 'SEARCH', css_class='btn btn-success btn-block',))
        )

        super(DataBlockSearchForm, self).__init__(*args, **kwargs)


class DataBlockDeleteConfirmForm(ModelForm):
    retyped_slug = forms.CharField(label='Re-type the Block ID of the Archive to confirm', max_length=22, required=True)
    class Meta:
        model = DataBlock
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML('<hr>'),
            HTML('<h3 style="color:red"><i class="fa fa-info" aria-hidden="true"></i> IMPORTANT: Data will be lost permanently</h3>'),
            HTML('<br>'),
            HTML('<hr>'),
            'retyped_slug',
            HTML('</p>'),
            HTML('<br>'),
        )
        self.helper.add_input(Submit('submit', 'Yes, I know what I am doing', css_class='btn btn-danger btn-block submit'))

        super(DataBlockDeleteConfirmForm, self).__init__(*args, **kwargs)

    def clean_retyped_slug(self):
        # Check that the project name they typed is correct
        slug = self.cleaned_data.get('retyped_slug')
        if not DataBlock.objects.filter(slug=slug).exists():
            raise forms.ValidationError('Data block with ID/Slug "{0}" does not exist'.format(slug))
        return slug


class DataBlockMaskForm(ModelForm, DataMaskFormMixin):
    start = forms.DateTimeField(required=False, label='Hide data before: (optional)',
                                help_text='Format: YYYY-MM-DD HH:MM:SS *in UTC time')
    end = forms.DateTimeField(required=False, label='Hide data after: (optional)',
                              help_text='Format: YYYY-MM-DD HH:MM:SS *in UTC time')

    class Meta:
        model = DataBlock
        fields = []

    def __init__(self, start, end, *args, **kwargs):
        assert 'instance' in kwargs
        block = kwargs['instance']

        self.helper = self.setup_crispy_helper(block)
        super(DataBlockMaskForm, self).__init__(*args, **kwargs)

        # Check for existing values, or forced values from parameter list (i.e. ?start=)
        mask_data = get_data_mask_date_range(block)
        if start:
            self.fields['start'].initial = str_to_dt_utc(start)
        elif mask_data and mask_data['start']:
            self.fields['start'].initial = str_to_dt_utc(mask_data['start'])
        if end:
            self.fields['end'].initial = str_to_dt_utc(end)
        elif mask_data and mask_data['end']:
            self.fields['end'].initial = str_to_dt_utc(mask_data['end'])

    def get_streams_to_mask(self, obj):
        """
        Get query set for valid streams to mask
        For example, we want to keep the trip start and trip ended around even after the trim

        :param obj: Device object
        :return: queryset
        """
        assert obj
        stream_qs = obj.streamids.filter(block=obj)

        return stream_qs

