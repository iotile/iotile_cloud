import json
from django.views.generic import UpdateView
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.contrib import messages

from apps.utils.views.basic import LoginRequiredAccessMixin

from .models import ConfigAttribute
from .forms import ConfigAttributeForm


class ConfigAttributeEditView(LoginRequiredAccessMixin, UpdateView):
    model = ConfigAttribute
    form_class = ConfigAttributeForm
    template_name = 's3file/text-editor-form.html'

    def form_valid(self, form):
        config = self.get_object()
        config.data = form.cleaned_data['txt_data']
        config.save()
        return HttpResponseRedirect(config.obj.get_absolute_url())

    def form_invalid(self, form):
        errors = json.loads(form.errors.as_json())
        for error in errors['txt_data']:
            messages.error(message=error['message'], request=self.request)
        config = self.get_object()

        return HttpResponseRedirect(config.get_edit_url())

    def get_context_data(self, **kwargs):
        context = super(ConfigAttributeEditView, self).get_context_data(**kwargs)
        context['title'] = _('Update Configuration Attribute')
        return context
