import logging

from django import forms as forms
from django.forms import ModelForm
from django.template.defaultfilters import slugify

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Button, Div, Field, Layout, Submit

from apps.org.models import Org

logger = logging.getLogger(__name__)

class OnboardOrgForm(ModelForm):
    class Meta:
        model = Org
        exclude = ['slug', 'created_by', 'users', 'is_vendor', 'avatar']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'

        self.helper.layout = Layout(
            'name',
            HTML('<h4>Important:</h4><ul>'),
            HTML('<li>Company (Organization) names have to be globally unique. '),
            HTML('<li>Only members of the same company can connect to the company’s devices and upload data.'),
            HTML('<li>You can invite others to join as members of the company you create. See <a href="http://help.iotile.cloud/article/21-how-do-i-invite-someone-to-my-company-account"><b>help</b></a>'),
            HTML('<li>If someone else has created your company (organization) account, request an invitation from them or contact Arch help. Do not create a new company.'),
            HTML('</ul><br>'),
        )
        self.helper.add_input(Submit('submit', 'Save and Next Step', css_class='btn btn-block btn-success submit'))

        super(OnboardOrgForm, self).__init__(*args, **kwargs)

    def clean_name(self):
        # Check that username is not used already
        name = self.cleaned_data.get('name')
        slug = slugify(name)
        if Org.objects.filter(slug=slug).exists():
            raise forms.ValidationError('Organization with this Company Name already exists'.format(name))
        return name
