import csv
import re

from apps.datablock.documents import DataBlockDocument
from apps.physicaldevice.documents import DeviceDocument
from apps.property.models import GenericPropertyOrgTemplate
from apps.s3images.views import S3ImageUploadView, S3ImageUploadSuccessEndpointView
from apps.utils.views.basic import LoginRequiredAccessMixin
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, CreateView, UpdateView
from elasticsearch_dsl import Q


from .forms import *
from .models import AuthAPIKey
from .roles import *
from .tasks import send_new_org_notification
from .worker.message_members import OrgSendMessageAction

logger = logging.getLogger(__name__)


class OrgAccessMixin(LoginRequiredAccessMixin):

    def get_basic_context(self):
        org = self.object

        if org:
            return org.permissions(self.request.user)
        return NO_PERMISSIONS_ROLE

    def get_object(self, queryset=None):

        obj = get_object_or_404(Org, slug=self.kwargs['slug'])
        if obj.created_by == self.request.user:
            # Event owner always have access
            return obj

        if self.request.user.is_staff:
            # Staff is allowed to see any event page
            return obj

        if obj.is_member(self.request.user):
            # All members have access to Org
            return obj

        raise PermissionDenied("User has no access to this group")


class OrgWriteAccessMixin(OrgAccessMixin):

    def get_basic_context(self):
        return self.org.permissions(self.request.user)

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.org = Org.objects.get_from_request(self.request)
        if self.org and not self.org.has_permission(self.request.user, 'can_manage_org_and_projects'):
            messages.error(self.request, 'You are not allowed to modify this org')
            return HttpResponseRedirect(self.org.get_absolute_url())
        return super(OrgWriteAccessMixin, self).dispatch(request, *args, **kwargs)


class OrgCanManageUsersMixin(OrgAccessMixin):

    def get_basic_context(self):
        return self.org.permissions(self.request.user)

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.org = Org.objects.get_from_request(self.request)
        if self.org and not self.org.has_permission(self.request.user, 'can_manage_users'):
            messages.error(self.request, 'You do not have access to this page')
            return HttpResponseRedirect(self.org.get_absolute_url())
        return super(OrgCanManageUsersMixin, self).dispatch(request, *args, **kwargs)


# Similar to OrgWriteAccessMixin, but fails if org is not specified
# (to be used in CreateView)
class OrgCanManageOrgMixin(OrgAccessMixin):

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.org = Org.objects.get_from_request(self.request)
        if not self.org or not self.org.has_permission(self.request.user, 'can_manage_org_and_projects'):
            raise PermissionDenied
        return super(OrgCanManageOrgMixin, self).dispatch(request, *args, **kwargs)


class OrgDetailView(OrgAccessMixin, DetailView):
    model = Org
    template_name = 'org/detail.html'

    def get_context_data(self, **kwargs):
        context = super(OrgDetailView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())
        context['membership_count'] = self.object.member_count()
        context['project_list'] = self.object.projects.all().order_by('name')
        context['fleet_list'] = self.object.fleets.order_by('name')
        context['webapp'] = getattr(settings, 'WEBAPP_BASE_URL')
        try:
            context['role'] = OrgMembership.objects.get(org=self.object, user=self.request.user).role
        except OrgMembership.DoesNotExist:
            context['role'] = ''
        return context


class OrgCreateView(OrgAccessMixin, CreateView):
    model = Org
    form_class = OrgCreateForm
    template_name = 'form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.save()
        self.object.register_user(user=self.request.user, is_admin=True, role='a0')
        send_new_org_notification(self.object)

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(OrgCreateView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())
        context['title'] = _('Setup New Company')
        context['back_url'] = self.request.META.get('HTTP_REFERER')
        context['orgs'] = Org.objects.user_orgs_qs(self.request.user)

        return context


class OrgEditView(OrgWriteAccessMixin, UpdateView):
    model = Org
    form_class = OrgEditForm
    template_name = 'org/org-edit-form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(OrgEditView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())
        return context


class OrgMembersView(OrgAccessMixin, DetailView):
    model = Org
    template_name = 'org/members.html'

    def get_context_data(self, **kwargs):
        context = super(OrgMembersView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())

        context['users'] = self.object.users.all()

        # Show inactive users, but only to accounts who can manage users
        if self.object.has_permission(self.request.user, 'can_manage_users'):
            context['inactive_members'] = OrgMembership.objects.filter(
                org=self.object, is_active=False, user__is_active=True
            ).order_by('user__username').select_related('user')

        context['members'] = OrgMembership.objects.filter(
            org=self.object, is_active=True, user__is_active=True
        ).order_by('user__username').select_related('user')

        try:
            is_owner = OrgMembership.objects.get(org=self.object, user=self.request.user).role == 'a0'
        except OrgMembership.DoesNotExist:
            is_owner = False

        context['is_owner'] = is_owner
        context['org'] = self.object

        return context


class OrgMembersCsvView(OrgMembersView):
    # Subclass of OrgMembersView, to produce a csv file
    template_name = 'org/org-members.csv'
    content_type = 'text/csv'


class OrgMembershipMessageView(OrgCanManageUsersMixin, UpdateView):
    model = Org
    form_class = OrgMembershipMessageForm
    template_name = 'org/form.html'

    def get_success_url(self):
        return reverse('org:members', kwargs={'slug': self.object.slug})

    def form_valid(self, form):
        self.object = form.save(commit=False)
        role = form.cleaned_data['role']
        message = form.cleaned_data['message']
        logger.info('Sending message to {} members of {}'.format(role, self.object))

        subject = '[IOTile Cloud] A message has been sent to you by {}'.format(self.request.user)

        args = {
            'user': self.request.user.slug,
            'org': self.object.slug,
            'role': role,
            'subject': subject,
            'message': message
        }

        OrgSendMessageAction.schedule(args=args)

        messages.info(self.request, 'Message has been sent to all {} members'.format(
            role if role != '-' else ''
        ))
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(OrgMembershipMessageView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())
        context['title'] = 'Message to members'

        return context

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        self.org = Org.objects.get_from_request(self.request)
        if self.org and not self.org.has_permission(self.request.user, 'can_manage_users'):
            messages.error(self.request, 'You are not allowed to manage users')
            return HttpResponseRedirect(self.org.get_absolute_url())
        return super(UpdateView, self).dispatch(request, *args, **kwargs)


class OrgSearchView(OrgAccessMixin, DetailView):
    model = Org
    template_name = 'org/search.html'
    query = ''
    form_class = DataBlockSearchForm

    def get_context_data(self, **kwargs):
        context = super(OrgSearchView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())

        self.query = self.request.POST.get('q')
        if self.query:
            f = re.findall('(\w+(:)\w+)', self.query)
            q = re.sub('(\w+(:)\w+)', '', self.query)
            # print('Searching for {}'.format(q))            
            # print('Filters: {}'.format(f))
            context['devices'] = self.search(DeviceDocument, q, f) if 'b' not in q.split() else []
            context['datablocks'] = self.search(DataBlockDocument, q, f)  if 'd' not in q.split() else []

        org_properties = GenericPropertyOrgTemplate.objects.filter(org=self.object).all()
        if not org_properties:
            org_properties = GenericPropertyOrgTemplate.objects.filter(org__slug='arch-systems').all()
        context['org_properties'] = [''.join(p.name.split()) for p in org_properties]
        
        context['form'] = DataBlockSearchForm
        context['query'] = self.query

        return context

    def search(self, document, query, filters):

        s = document.search()
        s = s.filter("term", org=self.object.slug)
        if query:
            s = s.query("multi_match", query=query, operator="and", type="cross_fields",
                fields=[
                    'title',
                    'label',
                    'properties_val',
                    'description',
                    'slug',
                    'template',
                    'sensorgraph',
                    'notes',
                    'created_by',
                    'claimed_by',
                ]
            )
        if filters:
            for f, delimiter in filters:
                key, value = f.split(delimiter)
                s = s.filter("nested", path="properties",
                    query=Q({
                        "bool" : {
                            "must" : [
                                Q("term", properties__key=key.lower()),
                                Q("match", properties__value=value)
                            ]
                        }
                    })
                )

        # for hit in s:
        #     pprint.pprint (hit)

        qs = s.to_queryset()

        # Highlight temporary disabled
        # response = s.execute()
        # for element, hit in zip(qs, response):
        #     if 'highlight' in hit.meta:
        #         for fragment in hit.meta.highlight:
        #             setattr(element, fragment, hit.meta.highlight[fragment])

        return qs
    
    def post(self, request, *args, **kwargs):
        self.object = Org.objects.get_from_request(self.request)

        if request.is_ajax():
            return render(request, 'org/search-results.html', self.get_context_data())
        else:
            return super(OrgSearchView, self).get(request, *args, **kwargs)


class OrgMembershipEditView(LoginRequiredAccessMixin, UpdateView):
    model = OrgMembership
    form_class = OrgMembershipForm
    template_name = 'org/form.html'

    def get_object(self, queryset=None):
        object = get_object_or_404(OrgMembership, pk=self.kwargs['pk'])
        self.org = object.org
        if self.org.has_permission(self.request.user, 'can_manage_users'):
            return object

        raise Http404

    def form_valid(self, form):
        self.object = form.save(commit=False)
        role = form.cleaned_data['role']
        self.object.permissions = dict(ORG_ROLE_PERMISSIONS[role])
        # Issue#1191: For now, hard code condition to set old is_admin
        self.object.is_org_admin = role in ['a0', 'a1']
        self.object.save()

        return HttpResponseRedirect(self.object.org.get_membership_url())

    def get_context_data(self, **kwargs):
        context = super(OrgMembershipEditView, self).get_context_data(**kwargs)
        context['title'] = _('Edit Organization Membership for {0}'.format(self.object.user))
        context['org'] = self.org
        context.update(self.object.permissions)
        return context

    def get_form_kwargs(self):
        kwargs = super( OrgMembershipEditView, self ).get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class OrgS3FileUploadView(OrgWriteAccessMixin, S3ImageUploadView):
    fineuploader_item_limit = 1

    def get_fineuploader_success_endpoint(self):
        return reverse('org:upload-image-success', kwargs={'slug': self.kwargs['slug']})


class OrgS3FileUploadSuccessEndpointView(S3ImageUploadSuccessEndpointView):
    org = None

    def post_s3image_save(self, s3image):
        self.org = get_object_or_404(Org, slug=self.kwargs['slug'])
        self.org.avatar = s3image
        self.org.save()

    def get_response_data(self, s3image):
        if self.org:
            redirectURL = self.org.get_absolute_url()
        else:
            redirectURL = s3image.get_absolute_url()

        response_data = {
            'redirectURL': redirectURL
        }
        return response_data


class OrgRolesView(OrgAccessMixin, DetailView):
    model = Org
    template_name = 'org/roles.html'

    def get_context_data(self, **kwargs):
        context = super(OrgRolesView, self).get_context_data(**kwargs)
        context.update(self.get_basic_context())
        context['roles'] = ['a0', 'a1', 'm1', 'r1']
        context['permissions'] = []
        for permission in ORG_PERMISSIONS:
            obj = {
                'label': ORG_ROLE_DESCRIPTIONS[permission]['label'],
                'description': ORG_ROLE_DESCRIPTIONS[permission]['description'],
                'hidden': ORG_ROLE_DESCRIPTIONS[permission]['hidden'],
            }
            for role in context['roles']:
                obj[role] = ORG_ROLE_PERMISSIONS[role][permission]
            context['permissions'].append(obj)
        return context


class OrgAPIKeysView(OrgCanManageOrgMixin, DetailView):
    model = AuthAPIKey
    template_name = 'org/manage-apikeys.html'
    # query_set = AuthAPIKey.objects.filter(org=self.object).select_related('org')

    def get_context_data(self, **kwargs):
        context = super(OrgAPIKeysView, self).get_context_data(**kwargs)
        # context.update(self.get_basic_context())
        context['is_owner'] = self.object.is_owner(self.request.user)
        context['is_staff'] = self.request.user.is_staff
        context['apikeys'] = AuthAPIKey.objects.filter(org=self.object).select_related('org')
        return context


class OrgAPIKeyCreateView(OrgCanManageOrgMixin, CreateView):
    model = AuthAPIKey
    form_class = OrgAPIKeyCreateForm
    template_name = 'form.html'

    def form_valid(self, form):
        self.object = form.save(commit=False)
        org = Org.objects.get_from_request(self.request)
        api_key, generated_key = AuthAPIKey.objects.create_key(
            name=self.object.name,
            revoked=self.object.revoked,
            expiry_date=self.object.expiry_date,
            org=org,
        )
        messages.info(self.request, 'Secret key is {}.'.format(generated_key) \
            + ' Please keep this carefully as it is not retrievable.')
        prefix, junk = generated_key.split('.')
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super(OrgAPIKeyCreateView, self).get_context_data(**kwargs)
        context['title'] = _('New M2M Key')
        return context

    def get_success_url(self):
        return reverse('org:apikeys', kwargs={'slug': self.org.slug})
