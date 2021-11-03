import logging
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.views.generic import CreateView, UpdateView, DeleteView
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.contrib import messages
from django.utils import timezone
from django.shortcuts import get_object_or_404

from allauth.account.adapter import get_adapter
from allauth.account.models import EmailAddress

from .models import *
from .forms import *

logger = logging.getLogger(__name__)


class InvitationSendView(CreateView):
    model = Invitation
    form_class = InvitationForm
    template_name = 'org/form.html'

    def get_success_url(self):
        return reverse('org:members', kwargs={'slug': self.object.org.slug})

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.org = self.org

        emails = EmailAddress.objects.filter(email=self.object.email)
        if emails.exists():
            assert (emails.count() == 1)
            email_address = emails.first()
            user = email_address.user
            if self.org.membership.filter(user=user).exists():
                messages.error(self.request, 'User with email {} already exists (but may be inactive)'.format(email_address))
                return HttpResponseRedirect(self.get_success_url())

        self.object.sent_by = self.request.user
        self.object.sent_on = timezone.now()
        self.object.save()
        self.object.send_email_notification(self.request)

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(InvitationSendView, self).get_context_data(**kwargs)
        context['title'] = _('Send invitation to join "{}"'.format(self.org.name))
        context['back_url'] = self.request.META.get('HTTP_REFERER')
        return context

    def get_form_kwargs(self):
        kwargs = super( InvitationSendView, self ).get_form_kwargs()
        kwargs['org'] = self.org
        kwargs['user'] = self.request.user
        return kwargs

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.org = get_object_or_404(Org, slug=self.kwargs['org_slug'])
        return super(InvitationSendView, self).dispatch(request, *args, **kwargs)


class InvitationResendView(UpdateView):
    model = Invitation
    form_class = InvitationResendForm
    template_name = 'org/form.html'

    def get_success_url(self):
        return reverse('org:members', kwargs={'slug': self.object.org.slug})

    def form_valid(self, form):
        self.object.sent_on = timezone.now()
        self.object.sent_by = self.request.user
        self.object.save()
        self.object.send_email_notification(self.request)
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(InvitationResendView, self).get_context_data(**kwargs)
        context['org'] = self.object.org
        return context

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(InvitationResendView, self).dispatch(request, *args, **kwargs)


class InvitationDeleteView(DeleteView):
    model = Invitation
    template_name = 'org/form.html'

    def get_success_url(self):
        return reverse('org:members', kwargs={'slug': self.object.org.slug})

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(InvitationDeleteView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(InvitationDeleteView, self).get_context_data(**kwargs)
        context['org'] = self.object.org
        context['form'] = InvitationDeleteConfirmForm()
        return context


class InvitationAcceptView(UpdateView):
    model = Invitation
    form_class = InvitationAcceptForm
    template_name = 'form.html'

    def get_success_url(self):
        return reverse('account_signup')

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()

        # First, check if there is an exsting user with this email
        emails = EmailAddress.objects.filter(email=self.object.email)
        if emails.exists():
            logger.info('Found existing user with email={}'.format(self.object.email))
            assert(emails.count() == 1)
            email_address = emails.first()
            user = email_address.user
            logger.info('User is @{}'.format(user.username))
            org = self.object.org
            if org.membership.filter(user=user, is_active=False).exists():
                messages.error(self.request, 'User is already a member of {} but is set to inactive. Contact the Admin'.format(org.name))
            else:
                with transaction.atomic():
                    org = self.object.org
                    org.register_user(user, role=self.object.role)
                    self.object.accepted = True
                    self.object.save()
                logger.info('New User added to {0}'.format(org))
                messages.success(self.request, 'Successfully accepted as member of {}'.format(org.name))

            return HttpResponseRedirect(org.get_absolute_url())
        else:
            self.request.session['invitation_id'] = str(self.object.id)
            get_adapter().stash_verified_email(self.request, self.object.email)
            return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(InvitationAcceptView, self).get_context_data(**kwargs)
        context['title'] = 'Your invitation'
        context['invitation'] = self.object
        return context

    def dispatch(self, request, *args, **kwargs):
        invitation = self.get_object()
        if invitation.accepted:
            messages.error(self.request, 'This invitation has already been accepted')
            return HttpResponseRedirect(reverse('home'))
        return super(InvitationAcceptView, self).dispatch(request, *args, **kwargs)
