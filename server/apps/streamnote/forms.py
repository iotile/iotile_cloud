from django.forms import ModelForm

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit

from .models import StreamNote


class StreamNoteForm(ModelForm):

    class Meta:
        model = StreamNote
        fields = ['note',]

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'note',
        )
        self.helper.add_input(Submit('submit', 'New Note', css_class='btn btn-block btn-success submit'))

        super(StreamNoteForm, self).__init__(*args, **kwargs)

        self.fields['note'].required = True
