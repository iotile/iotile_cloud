import logging
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.views.generic import CreateView, UpdateView, DeleteView, ListView, DetailView
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.http import Http404

from apps.physicaldevice.models import Device
from apps.utils.views.basic import LoginRequiredAccessMixin

from .models import *
from .forms import *

logger = logging.getLogger(__name__)


class GenericPropertyAccessMixin(LoginRequiredAccessMixin):

    def get_object(self, queryset=None):

        object = get_object_or_404(GenericProperty, pk=self.kwargs['pk'])
        return object
        # raise PermissionDenied("User has no access to this IOTile Property")

    def get_target(self):
        slug = self.kwargs['target_slug']
        name, obj = get_object_by_slug(slug)
        if not obj:
            raise Http404('Illegal slug format or object not found')
        return obj


class GenericPropertyWriteAccessMixin(GenericPropertyAccessMixin):

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        target = self.get_target()
        if not target.org.has_permission(self.request.user, 'can_modify_device_properties'):
            messages.error(self.request, 'You are not allowed to modify this property')
            return HttpResponseRedirect(target.get_absolute_url())
        return super(GenericPropertyAccessMixin, self).dispatch(request, *args, **kwargs)


class PropertyTemplateAccessMixin(LoginRequiredAccessMixin):
    org = None

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.org = Org.objects.get_from_request(self.request)
        # TODO: Need a better permission. Want to enable only for A0 roles
        if not self.org:
            messages.error(self.request, 'No access')
            return HttpResponseRedirect('/')
        if self.org and not self.org.has_permission(self.request.user, 'can_delete_org'):
            messages.error(self.request, 'User has no permissions to modify properties')
            return HttpResponseRedirect(self.org.get_absolute_url())
        return super(PropertyTemplateAccessMixin, self).dispatch(request, *args, **kwargs)


class GenericPropertyUpdateView(GenericPropertyWriteAccessMixin, UpdateView):
    model = GenericProperty
    form_class = GenericPropertyForm
    template_name = 'form.html'

    @transaction.atomic()
    def form_valid(self, form):
        self.object.name = form.cleaned_data['name']
        self.object.type = form.cleaned_data['type']
        self.object.str_value = form.cleaned_data['str_value']
        self.object.is_system = form.cleaned_data['is_system']
        try:
            self.object.save()
        except:
            raise ValueError("Property with this name already exists.")

        return HttpResponseRedirect(self.get_target().get_property_url())

    def get_context_data(self, **kwargs):
        context = super(GenericPropertyUpdateView, self).get_context_data(**kwargs)
        context['title'] = _('Edit IOTile Property')
        return context


class GenericPropertyCreateView(GenericPropertyWriteAccessMixin, CreateView):
    model = GenericProperty
    form_class = GenericPropertyForm
    template_name = 'form.html'

    def form_valid(self, form):
        name = form.cleaned_data['name']
        ptype = form.cleaned_data['type']
        str_value = form.cleaned_data['str_value']
        is_system = form.cleaned_data['is_system']
        target = self.kwargs['target_slug']
        created_by = self.request.user
        try:
            GenericProperty.objects.create(
                name=name, type=ptype, str_value=str_value, target=target, created_by=created_by, is_system=is_system
            )
        except:
            raise ValueError("Property with this name already exists.")
        return HttpResponseRedirect(self.get_target().get_property_url())

    def get_context_data(self, **kwargs):
        context = super(GenericPropertyCreateView, self).get_context_data(**kwargs)
        context['title'] = _('Add IOTile Property')
        return context

    def get_form_kwargs(self):
        kw = super(GenericPropertyCreateView, self).get_form_kwargs()
        kw['target_slug'] = self.kwargs['target_slug']
        return kw


class GenericPropertyDeleteView(GenericPropertyWriteAccessMixin, DeleteView):
    model = GenericProperty
    template_name = 'form.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.success_url = self.get_target().get_property_url()
        return super(GenericPropertyDeleteView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(GenericPropertyDeleteView, self).get_context_data(**kwargs)
        context['form'] = GenericPropertyDeleteConfirmForm()
        context['title'] = _('Delete IOTile Property')
        return context


class PropertyTemplateListView(PropertyTemplateAccessMixin, ListView):
    model = GenericPropertyOrgTemplate
    template_name = 'property/org-property-template-list.html'

    def get_queryset(self):
        if self.org:
            return GenericPropertyOrgTemplate.objects.filter(org=self.org)
        return GenericPropertyOrgTemplate.objects.none()

    def get_context_data(self, **kwargs):
        context = super(PropertyTemplateListView, self).get_context_data(**kwargs)
        context['org'] = self.org
        return context


class PropertyTemplateEnumListView(PropertyTemplateAccessMixin, DetailView):
    model = GenericPropertyOrgTemplate
    template_name = 'property/org-property-template-enum-list.html'

    def get_context_data(self, **kwargs):
        context = super(PropertyTemplateEnumListView, self).get_context_data(**kwargs)
        context['org'] = self.org
        return context


class PropertyTemplateEnumCreateView(PropertyTemplateAccessMixin, CreateView):
    model = GenericPropertyOrgEnum
    form_class = GenericPropertyOrgEnumForm
    template_name = 'org/form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.org = self.org
        self.object.save()
        return HttpResponseRedirect(self.object.template.get_absolute_url())

    def get_context_data(self, **kwargs):
        context = super(PropertyTemplateEnumCreateView, self).get_context_data(**kwargs)
        context['title'] = _('Add new property value')
        return context

    def get_form_kwargs(self):
        kw = super(PropertyTemplateEnumCreateView, self).get_form_kwargs()
        kw['org'] = self.org
        template_id = self.request.GET.get('template')
        if template_id:
            template = get_object_or_404(GenericPropertyOrgTemplate, pk=template_id)
            kw['template'] = template
        return kw


class PropertyTemplateEnumDeleteView(PropertyTemplateAccessMixin, DeleteView):
    model = GenericPropertyOrgEnum
    template_name = 'org/form.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        template = get_object_or_404(GenericPropertyOrgTemplate, pk=self.kwargs['template_pk'])
        self.success_url = template.get_absolute_url()
        return super(PropertyTemplateEnumDeleteView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(PropertyTemplateEnumDeleteView, self).get_context_data(**kwargs)
        context['form'] = GenericPropertyOrgEnumDeleteConfirmForm()
        context['title'] = _('Delete property value')
        return context
