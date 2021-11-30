import json

from django import forms
from django.conf import settings
from django.contrib.postgres.forms import SimpleArrayField
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, ButtonHolder, Div, Field, Layout, Submit

from apps.physicaldevice.models import Device
from apps.project.models import Project
from apps.stream.models import StreamId, StreamVariable

from .models import *


class StreamFilterDeleteForm(ModelForm):
    class Meta:
        model = StreamFilter
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Confirm delete', css_class='btn btn-block btn-danger'))
        self.helper.layout = Layout(
            HTML('<h3>Are you sure you want to delete stream filter {{ object.name }} ?</h3>'
                 '<h4>This confirmation will also delete all associated states, triggers and actions!</h4><br>')
        )
        super(StreamFilterDeleteForm, self).__init__(*args, **kwargs)


class StreamFilterResetForm(ModelForm):
    class Meta:
        model = StreamFilter
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Confirm delete', css_class='btn btn-block btn-danger'))
        self.helper.layout = Layout(
            HTML('<h3>Are you sure you want to reset filter {{ object.name }} {{ object.slug }} ?</h3>'
                 '<h4>The per-device current states will be removed!</h4><br>')
        )
        super(StreamFilterResetForm, self).__init__(*args, **kwargs)


class StateForm(ModelForm):

    class Meta:
        model = State
        fields = ['label']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))

        super(StateForm, self).__init__(*args, **kwargs)


class TransitionForm(ModelForm):
    src = forms.ModelChoiceField(
        label="From state",
        queryset=State.objects.none(),
        required=False
    )
    dst = forms.ModelChoiceField(
        label="To state",
        queryset=State.objects.none(),
        required=True
    )

    operator = forms.ChoiceField(label='Operator', choices=StreamFilterTrigger.OPERATOR_CHOICES)
    threshold = forms.FloatField(label='Threshold', required=False)

    class Meta:
        model = StateTransition
        fields = ['src', 'dst', 'operator', 'threshold']

    def __init__(self, filter, *args, **kwargs):
        self.filter = filter
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h3>Transition</h3>'),
            'src',
            'dst',
            HTML('<h3>Trigger</h3>'),
            Div(
                HTML('<h5 style="color:blue"><i class="fa fa-info" aria-hidden="true"></i>  The unit of the threshold you entered below is your current display unit : {{output_unit.unit_full}}</h5>'),
                Div('operator', css_class='col-sm-6 col-xs-12'),
                Div('threshold', css_class='col-sm-6 col-xs-12'),
                css_class='row'
            )
        )
        super(TransitionForm, self).__init__(*args, **kwargs)
        self.fields['src'].queryset = State.objects.filter(filter=filter)
        self.fields['dst'].queryset = State.objects.filter(filter=filter)

    def clean(self):
        data = self.cleaned_data
        count = StateTransition.objects.filter(filter=self.filter, src=data['src'], dst=data['dst']).count()
        if count > 0:
            raise forms.ValidationError("The transition from state {} to state {} has already existed !".format(data['src'], data['dst']))
        return data

class TransitionEditForm(ModelForm):
    src = forms.ModelChoiceField(
        label="From state",
        queryset=State.objects.none(),
        required=False
    )
    dst = forms.ModelChoiceField(
        label="To state",
        queryset=State.objects.none(),
        required=True
    )

    class Meta:
        model = StateTransition
        fields = ['src', 'dst']

    def __init__(self, filter, *args, **kwargs):
        self.filter = filter
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h3>Edit Transition</h3>'),
            'src',
            'dst',
        )
        super(TransitionEditForm, self).__init__(*args, **kwargs)
        self.fields['src'].queryset = State.objects.filter(filter=filter)
        self.fields['dst'].queryset = State.objects.filter(filter=filter)


class ActionTypeForm(ModelForm):

    class Meta:
        model = StreamFilterAction
        fields = ['type']

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h3>Choose an action type</h3>'),
            'type'
        )
        super(ActionTypeForm, self).__init__(*args, **kwargs)


class ActionDeleteForm(ModelForm):
    class Meta:
        model = StreamFilterAction
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Confirm delete', css_class='btn btn-block btn-danger'))
        self.helper.layout = Layout(
            HTML('<h3>Are you sure you want to delete action {{ object.get_type_display }}?</h3><br>'
                 '{% if object.output_stream %}Output stream: {{object.output_stream}} <br>{% endif%}'
                 '{% if object.extra_payload %}Extra payload: <br>'
                 '<ul>{% for key, value in object.extra_payload.items %}<li>{{ key }}: {{ value }}</li>{% endfor %}</ul>'
                 '{% endif%}'
                 '<h4>The following state will be affected: </h4>'
                 '<ul>{% for s in related_states %}<li> Filter {{s.filter}}: State {{s.label}}, action on {{s.on}}</li>{% endfor %}</ul>')
        )
        super(ActionDeleteForm, self).__init__(*args, **kwargs)


class StateDeleteForm(ModelForm):
    class Meta:
        model = State
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Confirm delete', css_class='btn btn-block btn-danger'))
        self.helper.layout = Layout(
            HTML('<h3>Are you sure to delete state {{ object.label }} ?</h3><br>'
                 '<h3 style="color:red;"><i class="fa fa-exclamation-triangle" aria-hidden="true"></i> Attention !!</h3> <h4>Your confirmation will also delete all transitions and actions linked to this state</h4>')
        )
        super(StateDeleteForm, self).__init__(*args, **kwargs)


class TransitionDeleteForm(ModelForm):
    class Meta:
        model = StateTransition
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Confirm delete', css_class='btn btn-block btn-danger'))
        self.helper.layout = Layout(
            HTML('<h3>Are you sure you want to delete transition from state {{ object.src.label.upper }} to {{ object.dst.label.upper }}?</h3><br>')
        )
        super(TransitionDeleteForm, self).__init__(*args, **kwargs)


class TriggerForm(ModelForm):
    class Meta:
        model = StreamFilterTrigger
        fields = ['operator', 'user_threshold']

    def __init__(self,  *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit', css_class='btn btn-success submit'))
        self.helper.layout = Layout(
            HTML('<h3>Add trigger to transition from state {{transition.src.label.upper}} to {{transition.dst.label.upper}}</h3>'),
            HTML('<h4>Current triggers: </h4>'),
            HTML('<ul>{%for t in transition.triggers.all%}<li>{{ t.get_operator_display }} {{ t.user_threshold }} {{ t.user_output_unit.unit_full }}</li>{% endfor%}</ul>'),
            Div(
                HTML('<h5 style="color:blue"><i class="fa fa-info" aria-hidden="true"></i>  The unit of the threshold you entered below is your current display unit : {{output_unit.unit_full}}</h5>'),
                Div('operator', css_class='col-sm-6 col-xs-12'),
                Div('user_threshold', css_class='col-sm-6 col-xs-12'),
                css_class='row'
            )
        )
        super(TriggerForm, self).__init__(*args, **kwargs)


class TriggerDeleteForm(ModelForm):
    class Meta:
        model = StreamFilterTrigger
        fields = []

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Confirm delete', css_class='btn btn-block btn-danger'))
        self.helper.layout = Layout(
            HTML('<h3>Are you sure you want to delete trigger: {{ object.get_operator_display }} {{ object.user_threshold }} {{ object.user_output_unit.unit_full }}?</h3><br>'
                 '<h4>The following transition will be affected: </h4>'
                 '<h5>Filter: {{object.filter.slug}} </h5>'
                 '<h5>Transition: From state {{object.transition.src.label}} to state {{object.transition.dst.label}}</h5>')
        )
        super(TriggerDeleteForm, self).__init__(*args, **kwargs)




