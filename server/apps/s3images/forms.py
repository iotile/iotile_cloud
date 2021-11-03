from django.forms import ModelForm
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit

from .models import *


class S3ImageTitleUpdateForm(ModelForm):
    class Meta:
        model = S3Image
        fields = ['title',]

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', _('Submit'), css_class='btn btn-default submit'))

        super(S3ImageTitleUpdateForm, self).__init__(*args, **kwargs)

