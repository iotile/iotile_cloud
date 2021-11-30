from django import forms
from django.forms import ModelForm

from crispy_forms.bootstrap import FieldWithButtons
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, ButtonHolder, Div, Field, Layout, Submit

from apps.physicaldevice.models import Device
from apps.property.models import GenericProperty, GenericPropertyOrgEnum, GenericPropertyOrgTemplate


class SxdDeviceForm(forms.Form):
    external_id = forms.CharField(label='External ID (Saver ID)', max_length=38, required=True)
    reset = forms.BooleanField(label='Reset Data ID', required=False)
    _project = None

    def __init__(self, project, *args, **kwargs):
        assert(project)

        intro = """
        <h2>
        Process to manually upload SXd Files (saver files)
        </h2>
        <p>
        <b>Step 1:</b> Find the associated IOTile device for the given Saver.
        </p>
        <p>
        <b>Step 2:</b> Ensure all trip properties are already entered, or if not, enter them.
        </p>
        <p>
        <b>Step 3:</b> Once the properties are created, you will be able to upload the SXd file.
        </p>
        <br>
        """
        reset_helper = """
        <small>
        This uploader will ignore any data with a timestamp older than the last uploaded timestamp.
        This is done to prevent duplicating data. 
        But if you are loading a trip that was ended before the last trip you uploaded,
        you can click this option to reset the last ID, and allow the older data to be uploaded.
        If this option is checked, and you upload a duplicated trip,
        <span style='color:red'>there will be no way to prevent adding this duplicated trip</span>.
        </small>
        """

        self._project = project
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            HTML(intro),
            'external_id',
            HTML('<p> *The Saver ID is usually of the form XXXX-XXX (e.g. 0542-058)</p>'),
            HTML('<br>'),
            'reset',
            HTML(reset_helper),
            HTML('<br>'),
            HTML('<br>')
        )
        self.helper.add_input(
            Submit('submit', 'Find device and go to step 2 (trip properties)', css_class='btn btn-success btn-block submit'))

        super(SxdDeviceForm, self).__init__(*args, **kwargs)

    def clean_external_id(self):
        # Check that username is not used already
        external_id = self.cleaned_data.get('external_id')
        try:
            device = Device.objects.get(external_id=external_id, project=self._project)
        except Device.DoesNotExist:
            raise forms.ValidationError('No device found in project with external_id={}'.format(external_id))

        return device


class SxdPropertiesForm(ModelForm):
    class Meta:
        model = Device
        fields = []

    def __init__(self, *args, **kwargs):
        """
        Dynamically create form with all required properties for this Org
        """
        super(SxdPropertiesForm, self).__init__(*args, **kwargs)
        if 'instance' in kwargs:
            device = kwargs['instance']
            org = device.org

            properties = GenericProperty.objects.object_properties_qs(device)
            p_map = {}
            for p in properties:
                p_map[p.name] = p.value

            property_templates = GenericPropertyOrgTemplate.objects.filter(org=org)

            for pt in property_templates:
                field_name = pt.name
                if pt.enums.exists():
                    self.fields[field_name] = forms.ModelChoiceField(
                        label=pt.name,
                        queryset=pt.enums.all().order_by('value'),
                        required=False
                    )
                    if pt.name in p_map:
                        try:
                            value_enum = GenericPropertyOrgEnum.objects.get(template=pt, value=p_map[pt.name])
                            self.initial[field_name] = value_enum
                        except GenericPropertyOrgEnum.DoesNotExist:
                            pass
                else:

                    if 'input_type' in pt.extra and pt.extra['input_type'] == 'textarea':
                        self.fields[field_name] = forms.CharField(label=pt.name, required=False, widget=forms.Textarea(attrs={'rows': 5}))
                    else:
                        self.fields[field_name] = forms.CharField(label=pt.name, required=False)

                    if pt.name in p_map:
                        self.initial[field_name] = p_map[pt.name]
                    elif pt.default:
                        self.initial[field_name] = pt.default

            self.helper = FormHelper()
            self.helper.form_method = 'post'
            self.helper.layout = Layout(
                HTML('<h2>Properties for device {} ({})</h2>'.format(device.slug, device.external_id))
            )
            sorted_property_template = sorted(property_templates, key=lambda x: x.extra['order'] if 'order' in x.extra else 0)
            for pt in sorted_property_template:
                self.helper.layout.append(pt.name)

            self.helper.add_input(
                Submit('submit', 'Save properties and go to step 3 (file upload)', css_class='btn btn-success btn-block submit'))


class DeviceStartTripForm(ModelForm):
    class Meta:
        model = Device
        fields = []

    def __init__(self, *args, **kwargs):
        """
        Dynamically create form with all required properties for this Org
        """
        super(DeviceStartTripForm, self).__init__(*args, **kwargs)
        if 'instance' in kwargs:
            device = kwargs['instance']
            org = device.org

            properties = GenericProperty.objects.object_properties_qs(device)
            p_map = {}
            for p in properties:
                p_map[p.name] = p.value

            property_templates = GenericPropertyOrgTemplate.objects.filter(org=org)
            for pt in property_templates:
                field_name = pt.name
                if pt.enums.exists():
                    self.fields[field_name] = forms.ModelChoiceField(
                        label=pt.name,
                        queryset=pt.enums.all().order_by('value'),
                        required=False
                    )
                    if pt.name in p_map:
                        try:
                            value_enum = GenericPropertyOrgEnum.objects.get(template=pt, value=p_map[pt.name])
                            self.initial[field_name] = value_enum
                        except GenericPropertyOrgEnum.DoesNotExist:
                            pass
                else:

                    if 'input_type' in pt.extra and pt.extra['input_type'] == 'textarea':
                        self.fields[field_name] = forms.CharField(label=pt.name, required=False, widget=forms.Textarea(attrs={'rows': 5}))
                    else:
                        self.fields[field_name] = forms.CharField(label=pt.name, required=False)

                    if pt.name in p_map:
                        self.initial[field_name] = p_map[pt.name]
                    elif pt.default:
                        self.initial[field_name] = pt.default

            self.helper = FormHelper()
            self.helper.form_method = 'post'
            self.helper.layout = Layout(
                HTML('<h2>Properties for device {}</h2>'.format(device.slug))
            )
            sorted_property_template = sorted(property_templates, key=lambda x: x.extra['order'] if 'order' in x.extra else 0)
            for pt in sorted_property_template:
            # for pt in property_templates:    # !! DELETE ME !! 
                self.helper.layout.append(pt.name)

            self.helper.add_input(
                Submit('submit', 'Start trip', css_class='btn btn-success btn-block submit'))
