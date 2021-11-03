import logging
from django.views.generic import DetailView, CreateView, UpdateView, ListView, DeleteView, TemplateView
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.contrib import messages

from apps.utils.views.basic import LoginRequiredAccessMixin
from apps.streamdata.utils import get_stream_output_unit

from .forms import *
from .models import *
from .actions.factory import action_form_class
from .cache_utils import set_current_cached_filter_state_for_slug, clear_serialized_filter_for_slug


def get_filter_output_unit(f):
    if f.input_stream:
        return get_stream_output_unit(f.input_stream)
    else:
        return f.variable.output_unit


def get_filter_output_mdo(f):
    output_unit = get_filter_output_unit(f)
    if output_unit:
        return output_unit.get_mdo_helper()
    return None


class StreamFilterAccessMixin(LoginRequiredAccessMixin):

    def get_object(self, queryset=None):
        if 'filter_slug' in self.kwargs:
            filter_slug = self.kwargs['filter_slug']
        else:
            filter_slug = self.kwargs['slug']
        object = get_object_or_404(StreamFilter, slug=filter_slug)
        if object.has_access(self.request.user):
            return object

        raise PermissionDenied("User has no access to this Stream Filter")

    def get_org_and_project_context_data(self, this_filter):
        return {
            'project': this_filter.project,
            'org': this_filter.project.org
        }


class StreamFilterDetailView(StreamFilterAccessMixin, DetailView):
    model = StreamFilter
    template_name = 'streamfilter/filter-detail.html'

    def get_context_data(self, **kwargs):
        context = super(StreamFilterDetailView, self).get_context_data(**kwargs)
        org = self.object.project.org
        context['is_admin_or_staff'] = org.is_admin(self.request.user) or self.request.user.is_staff
        context.update(self.get_org_and_project_context_data(self.object))
        return context


class StreamFilterDeleteView(StreamFilterAccessMixin, UpdateView):
    model = StreamFilter
    template_name = 'project/form.html'
    form_class = StreamFilterDeleteForm

    def get_context_data(self, **kwargs):
        context = super(StreamFilterDeleteView, self).get_context_data(**kwargs)
        this_filter = self.object
        context.update(self.get_org_and_project_context_data(this_filter))
        return context

    def form_valid(self, form):
        project = self.object.project
        for transition in self.object.transitions.all():
            for trigger in transition.triggers.all():
                trigger.delete()
            transition.delete()
        self.object.delete()
        messages.success(self.request, "Filter has been scheduled for deletion")
        return HttpResponseRedirect(reverse('org:project:detail', kwargs={'org_slug': project.org.slug, 'pk': project.pk}))


class StreamFilterResetView(StreamFilterAccessMixin, UpdateView):
    model = StreamFilter
    template_name = 'project/form.html'
    form_class = StreamFilterResetForm

    def form_valid(self, form):
        clear_serialized_filter_for_slug(self.object.slug)
        messages.success(self.request, "Filter has been set to reset")
        return HttpResponseRedirect(self.object.get_absolute_url())

    def get_context_data(self, **kwargs):
        context = super(StreamFilterResetView, self).get_context_data(**kwargs)
        filter_slug = self.kwargs.get('slug')
        this_filter = get_object_or_404(StreamFilter, slug=filter_slug)
        context.update(self.get_org_and_project_context_data(this_filter))
        return context


class StateCreateView(StreamFilterAccessMixin, CreateView):
    model = State
    template_name = "project/form.html"
    form_class = StateForm

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.filter = StreamFilter.objects.get(slug=self.kwargs['slug'])
        self.object.save()
        self.kwargs['filter_slug'] = self.kwargs.pop('slug')
        self.kwargs['slug'] = self.object.slug
        return HttpResponseRedirect(reverse("filter:state-detail", kwargs=self.kwargs))

    def get_context_data(self, **kwargs):
        context = super(StateCreateView, self).get_context_data(**kwargs)
        filter_slug = self.kwargs.get('slug')
        this_filter = get_object_or_404(StreamFilter, slug=filter_slug)
        context.update(self.get_org_and_project_context_data(this_filter))
        return context


class StateDetailView(StreamFilterAccessMixin, DetailView):
    model = State
    template_name = "streamfilter/state-detail.html"
    queryset = State.objects.none()

    def get_object(self, queryset=None):
        obj = get_object_or_404(State, filter__slug=self.kwargs['filter_slug'], slug=self.kwargs['slug'])
        return obj

    def get_context_data(self, **kwargs):
        context = super(StateDetailView, self).get_context_data(**kwargs)
        this_filter = self.object.filter
        context.update(self.get_org_and_project_context_data(this_filter))
        return context


class StateDeleteView(StreamFilterAccessMixin, UpdateView):
    model = State
    template_name = 'project/form.html'
    form_class = StateDeleteForm
    queryset = State.objects.none()

    def get_object(self, queryset=None):
        obj = get_object_or_404(State, filter__slug=self.kwargs['filter_slug'], slug=self.kwargs['slug'])
        return obj

    def get_context_data(self, **kwargs):
        context = super(StateDeleteView, self).get_context_data(**kwargs)
        filter_slug = self.kwargs.get('filter_slug')
        this_filter = get_object_or_404(StreamFilter, slug=filter_slug)
        context.update(self.get_org_and_project_context_data(this_filter))
        return context

    def form_valid(self, form):
        f = self.object.filter
        self.object.delete()
        # This will also delete linked transitions and triggers by database cascade deletion
        messages.success(self.request, "State has been scheduled for deletion")
        return HttpResponseRedirect(f.get_absolute_url())


class TransitionCreateView(StreamFilterAccessMixin, CreateView):
    model = StateTransition
    template_name = "project/form.html"
    form_class = TransitionForm

    def get_form_kwargs(self):
        kwargs = super(TransitionCreateView, self).get_form_kwargs()
        self.filter = StreamFilter.objects.get(slug=self.kwargs['slug'])
        self.output_unit = get_filter_output_unit(self.filter)
        kwargs['filter'] = get_object_or_404(StreamFilter, slug=self.kwargs['slug'])
        return kwargs

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.filter = StreamFilter.objects.get(slug=self.kwargs['slug'])
        self.object.save()
        op = form.cleaned_data['operator']
        threshold = form.cleaned_data['threshold']
        self.output_unit = get_filter_output_unit(self.filter)
        output_mdo = get_filter_output_mdo(self.filter)
        if op != 'bu':
            if output_mdo:
                logger.info('Using MDO={}'.format(str(output_mdo)))
                threshold_internal_value = output_mdo.compute_reverse(threshold)
            else:
                threshold_internal_value = threshold
        else:
            threshold_internal_value = 0
        trigger = StreamFilterTrigger.objects.create(operator=op,
                                                     user_threshold=threshold,
                                                     user_output_unit=self.output_unit,
                                                     threshold=threshold_internal_value,
                                                     created_by=self.request.user,
                                                     filter=self.object.filter,
                                                     transition=self.object)
        logger.info('Added trigger ({0}) user_threshold={1}, threshold={2}'.format(op, trigger.user_threshold, threshold))
        return HttpResponseRedirect(reverse("filter:detail", kwargs=self.kwargs))

    def get_context_data(self, **kwargs):
        context = super(TransitionCreateView, self).get_context_data(**kwargs)
        context['output_unit'] = self.output_unit
        filter_slug = self.kwargs.get('slug')
        this_filter = get_object_or_404(StreamFilter, slug=filter_slug)
        context.update(self.get_org_and_project_context_data(this_filter))
        return context


class TransitionDeleteView(StreamFilterAccessMixin, UpdateView):
    model = StateTransition
    template_name = 'project/form.html'
    form_class = TransitionDeleteForm
    queryset = StateTransition.objects.none()

    def get_object(self, queryset=None):
        return get_object_or_404(StateTransition, filter__slug=self.kwargs['filter_slug'], pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super(TransitionDeleteView, self).get_context_data(**kwargs)
        this_filter = self.object.filter
        context.update(self.get_org_and_project_context_data(this_filter))
        return context

    def form_valid(self, form):
        triggers = self.object.triggers.all()
        for t in triggers:
            t.delete()
        self.object.delete()
        messages.success(self.request, "Transition has been scheduled for deletion")
        self.kwargs['slug'] = self.kwargs['filter_slug']
        self.kwargs.pop('filter_slug')
        self.kwargs.pop('pk')
        return HttpResponseRedirect(reverse("filter:detail", kwargs=self.kwargs))


class TransitionEditView(StreamFilterAccessMixin, UpdateView):
    model = StateTransition
    template_name = 'project/form.html'
    form_class = TransitionEditForm
    queryset = StateTransition.objects.none()

    def get_object(self, queryset=None):
        return get_object_or_404(StateTransition, filter__slug=self.kwargs['filter_slug'], pk=self.kwargs['pk'])

    def get_form_kwargs(self):
        kwargs = super(TransitionEditView, self).get_form_kwargs()
        kwargs['filter'] = self.object.filter
        return kwargs

    def get_context_data(self, **kwargs):
        context = super(TransitionEditView, self).get_context_data(**kwargs)
        this_filter = self.object.filter
        context['output_unit'] =  get_filter_output_unit(this_filter)
        context.update(self.get_org_and_project_context_data(this_filter))
        return context

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()
        self.kwargs['slug'] = self.kwargs['filter_slug']
        self.kwargs.pop('filter_slug')
        self.kwargs.pop('pk')
        return HttpResponseRedirect(reverse("filter:detail", kwargs=self.kwargs))


class TriggerAddView(StreamFilterAccessMixin, CreateView):
    model = StreamFilterTrigger
    template_name = "project/form.html"
    form_class = TriggerForm

    def get_context_data(self, **kwargs):
        context = super(TriggerAddView, self).get_context_data(**kwargs)
        transition = StateTransition.objects.get(filter__slug=self.kwargs['filter_slug'], pk=self.kwargs['pk'])
        context['transition'] = transition
        context['output_unit'] = get_filter_output_unit(transition.filter)
        this_filter = transition.filter
        context.update(self.get_org_and_project_context_data(this_filter))
        return context

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        transition = StateTransition.objects.get(filter__slug=self.kwargs['filter_slug'], pk=self.kwargs['pk'])
        self.object.transition = transition
        self.object.filter = StreamFilter.objects.get(slug=self.kwargs['filter_slug'])
        output_mdo = get_filter_output_mdo(self.object.filter)
        output_unit = get_filter_output_unit(self.object.filter)
        if output_mdo:
            # logger.info('Using MDO={}'.format(str(output_mdo)))
            threshold_internal_value = output_mdo.compute_reverse(self.object.user_threshold)
        else:
            threshold_internal_value = self.object.user_threshold
        self.object.user_output_unit = output_unit
        self.object.threshold = threshold_internal_value
        self.object.save()
        logger.info('Added trigger ({0}) user_threshold={1}, threshold={2}'.format(
            self.object.operator, self.object.user_threshold, self.object.threshold
        ))
        self.kwargs['slug'] = self.kwargs['filter_slug']
        self.kwargs.pop('filter_slug')
        self.kwargs.pop('pk')
        return HttpResponseRedirect(reverse("filter:detail", kwargs=self.kwargs))


class TriggerDeleteView(StreamFilterAccessMixin, UpdateView):
    model = StreamFilterTrigger
    template_name = 'project/form.html'
    form_class = TriggerDeleteForm
    queryset = StreamFilterTrigger.objects.none()

    def get_object(self, queryset=None):
        obj = get_object_or_404(StreamFilterTrigger, pk=self.kwargs['pk'])
        return obj

    def get_context_data(self, **kwargs):
        context = super(TriggerDeleteView, self).get_context_data(**kwargs)
        this_filter = self.object.filter
        context.update(self.get_org_and_project_context_data(this_filter))
        return context

    def form_valid(self, form):
        self.object.delete()
        messages.success(self.request, "Trigger has been scheduled for deletion")
        return HttpResponseRedirect(reverse("filter:detail", kwargs={'slug': self.kwargs['filter_slug']}))


class TriggerEditView(StreamFilterAccessMixin, UpdateView):
    model = StreamFilterTrigger
    template_name = 'project/form.html'
    form_class = TriggerForm
    queryset = StreamFilterTrigger.objects.none()

    def get_object(self, queryset=None):
        obj = get_object_or_404(StreamFilterTrigger, pk=self.kwargs['pk'])
        return obj

    def get_context_data(self, **kwargs):
        context = super(TriggerEditView, self).get_context_data(**kwargs)
        transition = self.object.transition
        context['transition'] = transition
        context['output_unit'] =  get_filter_output_unit(transition.filter)
        this_filter = transition.filter
        context.update(self.get_org_and_project_context_data(this_filter))
        return context

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.filter = StreamFilter.objects.get(slug=self.kwargs['filter_slug'])
        output_mdo = get_filter_output_mdo(self.object.filter)
        output_unit = get_filter_output_unit(self.object.filter)
        if self.object.operator != 'bu':
            if output_mdo:
                threshold_internal_value = output_mdo.compute_reverse(self.object.user_threshold)
            else:
                threshold_internal_value = self.object.user_threshold
        else:
            threshold_internal_value = 0
        self.object.user_output_unit = output_unit
        self.object.threshold = threshold_internal_value
        self.object.save()
        logger.info('Changed trigger ({0}) user_threshold={1}, threshold={2}'.format(
            self.object.operator, self.object.user_threshold, self.object.threshold
        ))
        self.kwargs['slug'] = self.kwargs['filter_slug']
        self.kwargs.pop('filter_slug')
        self.kwargs.pop('pk')
        return HttpResponseRedirect(reverse("filter:detail", kwargs=self.kwargs))



class StreamFilterActionTypeCreateView(StreamFilterAccessMixin, CreateView):
    model = StreamFilterAction
    template_name = "project/form.html"
    form_class = ActionTypeForm

    def get_context_data(self, **kwargs):
        context = super(StreamFilterActionTypeCreateView, self).get_context_data(**kwargs)
        this_filter = StreamFilter.objects.get(slug=self.kwargs['filter_slug'])
        context.update(self.get_org_and_project_context_data(this_filter))
        return context

    def form_valid(self, form):
        if 'on' in self.request.GET:
            self.kwargs['type'] = form.cleaned_data['type']
            return HttpResponseRedirect(reverse("filter:action-create", kwargs=self.kwargs) + "?on={}".format(self.request.GET['on']))
        else:
            messages.error(self.request, "Missing query parameter")
            self.kwargs['slug'] = self.kwargs['filter_slug']
            self.kwargs.pop('filter_slug')
            return HttpResponseRedirect(reverse("filter:detail", kwargs=self.kwargs))


class StreamFilterActionCreateView(StreamFilterAccessMixin, CreateView):
    model = StreamFilterAction
    template_name = "project/form.html"
    form_class = None

    def get(self, *args, **kwargs):
        action_class = action_form_class(self.kwargs['type'])
        if action_class:
            return super(StreamFilterActionCreateView, self).get(*args, **kwargs)
        else:
            messages.error(self.request, "The type of action you requested is not supported at this moment")
            self.kwargs.pop('type')
            return HttpResponseRedirect(reverse("filter:action-create-type", kwargs=self.kwargs) + "?on={}".format(self.request.GET['on']))

    def get_form_class(self):
        action_class = action_form_class(self.kwargs['type'])
        if action_class:
            return action_class
        else:
            messages.error(self.request, "The type of action you requested is not supported at this moment")
            self.kwargs.pop('type')
            return HttpResponseRedirect(reverse("filter:action-create-type", kwargs=self.kwargs) + "?on={}".format(self.request.GET['on']))

    def get_form_kwargs(self):
        kw = super(StreamFilterActionCreateView, self).get_form_kwargs()
        kw['user'] = self.request.user
        this_filter = StreamFilter.objects.get(slug=self.kwargs['filter_slug'])
        kw['project'] = this_filter.project
        return kw

    def get_context_data(self, **kwargs):
        context = super(StreamFilterActionCreateView, self).get_context_data(**kwargs)
        this_filter = StreamFilter.objects.get(slug=self.kwargs['filter_slug'])
        context.update(self.get_org_and_project_context_data(this_filter))
        return context

    def form_valid(self, form):
        self.object = form.save(commit=False)
        '''
        if 'output_stream' in form.cleaned_data:
            self.object.output_stream = form.cleaned_data['output_stream']
        '''
        self.object.created_by = self.request.user
        self.object.type = self.kwargs['type']
        self.object.extra_payload = form.cleaned_data['extra_payload']
        state = get_object_or_404(State, filter__slug=self.kwargs['filter_slug'], slug=self.kwargs['slug'])
        if self.request.GET['on'] in ['entry', 'exit']:
            self.object.state = state
            self.object.on = self.request.GET['on']
        self.object.save()

        self.kwargs.pop('type')
        return HttpResponseRedirect(reverse("filter:state-detail", kwargs=self.kwargs))


class StreamFilterActionEditView(StreamFilterAccessMixin, UpdateView):
    model = StreamFilterAction
    template_name = 'project/form.html'
    queryset = StreamFilterAction.objects.none()

    def get_object(self, queryset=None):
        obj = get_object_or_404(StreamFilterAction, pk=self.kwargs['pk'])
        return obj

    def get_form_class(self):
        action = self.object
        action_class = action_form_class(action.type)
        if action_class:
            return action_class
        else:
            messages.error(self.request, "The type of action you requested is not supported at this moment")
            self.kwargs.pop('type')
            return HttpResponseRedirect(reverse("filter:action-create-type", kwargs=self.kwargs) + "?on={}".format(self.request.GET['on']))

    def get_form_kwargs(self):
        kw = super(StreamFilterActionEditView, self).get_form_kwargs()
        kw['user'] = self.request.user
        this_filter = StreamFilter.objects.get(slug=self.kwargs['filter_slug'])
        kw['project'] = this_filter.project
        return kw

    def get_context_data(self, **kwargs):
        context = super(StreamFilterActionEditView, self).get_context_data(**kwargs)
        this_filter = StreamFilter.objects.get(slug=self.kwargs['filter_slug'])
        context.update(self.get_org_and_project_context_data(this_filter))
        return context

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.extra_payload = form.cleaned_data['extra_payload']
        self.object.save()
        args = {
            'filter_slug': self.kwargs['filter_slug'],
            'slug': self.object.state.slug
        }
        return HttpResponseRedirect(reverse("filter:state-detail", kwargs=args))


class StreamFilterActionDeleteView(StreamFilterAccessMixin, UpdateView):
    model = StreamFilterAction
    template_name = 'project/form.html'
    form_class = ActionDeleteForm
    queryset = StreamFilterAction.objects.none()

    def get_object(self, queryset=None):
        obj = get_object_or_404(StreamFilterAction, pk=self.kwargs['pk'])
        return obj

    def form_valid(self, form):
        self.object.delete()
        messages.success(self.request, "Action has been scheduled for deletion")
        return HttpResponseRedirect(reverse("filter:detail", kwargs={'slug': self.kwargs['filter_slug']}))

    def get_context_data(self, **kwargs):
        context = super(StreamFilterActionDeleteView, self).get_context_data(**kwargs)
        st = self.object.state
        related_states = [{
            'filter': st.filter.slug,
            'label': st.label,
            'on': self.object.on
        }]
        context['related_states'] = related_states
        this_filter = StreamFilter.objects.get(slug=self.kwargs['filter_slug'])
        context.update(self.get_org_and_project_context_data(this_filter))
        return context
