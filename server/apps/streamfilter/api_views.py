from django.shortcuts import get_object_or_404

import django_filters
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.org.permissions import IsMemberOnly

from .cache_utils import cached_serialized_filter_for_slug
from .serializers import *


class APIStreamFilterViewSet(viewsets.ModelViewSet):
    """
    Not Documented. For Internal Use Only.
    """
    lookup_field = 'slug'
    queryset = StreamFilter.objects.none()
    serializer_class = StreamFilterSerializer
    permission_classes = (IsMemberOnly,)
    filterset_fields = ('project',)
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)

    def get_queryset(self):
        """
        This view should return a list of all records
        """

        if self.request.user.is_staff and self.request.GET.get('staff', ''):
            qs = StreamFilter.objects.all()
        else:
            qs = StreamFilter.objects.user_stream_filter_qs(self.request.user)

        return qs.prefetch_related('transitions', 'states', 'triggers')

    def get_object(self):
        slug = self.kwargs['slug']
        f = get_object_or_404(StreamFilter, slug=slug)

        if f.has_access(self.request.user):
            return f

        raise PermissionDenied

    def perform_create(self, serializer):
        # Include the owner attribute directly, rather than from request data.
        instance = serializer.save(created_by=self.request.user)

    @action(methods=['get', 'post', 'delete', 'put'], detail=True)
    def state(self, request, slug=None):
        """
        POST: Create a new state. Fields:
        - label (required): State's label
        PUT: Update a state. Required field : label
        """
        obj = get_object_or_404(StreamFilter, slug=slug)
        if request.method == 'GET':
            states = obj.states.all()
            serializer = StateReadOnlySerializer(states, many=True)
            return Response(serializer.data)
        elif request.method == 'POST':
            serializer = StateSerializer(data=request.data, context={'filter': obj, 'request': request})
            if serializer.is_valid():
                serializer.save(filter=obj, created_by=self.request.user)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        elif request.method == 'DELETE':
            state = get_object_or_404(State, filter=obj, **request.data)
            state.delete()
            return Response(request.data, status=status.HTTP_204_NO_CONTENT)
        elif request.method == 'PUT':
            if 'label' not in request.data:
                return Response({'error': 'State label is required'}, status=status.HTTP_400_BAD_REQUEST)
            state = get_object_or_404(State, filter=obj, label=request.data['label'])
            serializer = StateSerializer(state, data=request.data, context={'filter': obj, 'request': request})
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['get', 'post', 'delete', 'put'], detail=True)
    def transition(self, request, slug=None):
        """
        POST - create a transition with trigger information (optional)
        Fields :
        - src: (required) State id
        - dst: (required) State id
        - triggers: (optional) array of payload for creating new triggers. Example "triggers": [{"operator": "ge", "user_threshold": 10}]
        PUT: Update a transition (triggers). Required fields: src, dst
        """
        obj = get_object_or_404(StreamFilter, slug=slug)
        if request.method == 'GET':
            transitions = obj.transitions.all()
            serializer = StateTransitionReadOnlySerializer(transitions, many=True)
            return Response(serializer.data)
        elif request.method == 'POST':
            serializer = StateTransitionSerializer(data=request.data, context={'filter': obj, 'request': request})
            if serializer.is_valid():
                serializer.save(filter=obj, created_by=self.request.user)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        elif request.method == 'DELETE':
            transition = get_object_or_404(StateTransition, filter=obj, **request.data)
            transition.delete()
            return Response(request.data, status=status.HTTP_204_NO_CONTENT)
        elif request.method == 'PUT':
            if 'src' not in request.data or 'dst' not in request.data:
                return Response({'error': 'src and dst are required'}, status=status.HTTP_400_BAD_REQUEST)
            transition = get_object_or_404(StateTransition, filter=obj, src=request.data['src'], dst=request.data['dst'])
            serializer = StateTransitionSerializer(transition, data=request.data, context={'filter': obj, 'request': request})
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['get', 'post', 'delete'], detail=True)
    def trigger(self, request, slug=None):
        """
        POST: Create a new trigger.
        Fields :
        - user_threshold: (required) Num
        - operator: (required) Str
        - transition: (optional) id of the transition that this trigger should belong to
        """
        obj = get_object_or_404(StreamFilter, slug=slug)
        if request.method == 'GET':
            triggers = obj.triggers.all()
            serializer = StreamFilterTriggerSerializer(triggers, many=True)
            return Response(serializer.data)
        elif request.method == 'POST':
            serializer = StreamFilterTriggerSerializer(data=request.data, context={'filter': obj})
            if serializer.is_valid():
                serializer.save(created_by=self.request.user)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        elif request.method == 'DELETE':
            if 'id' not in request.data:
                return Response({'error': 'Trigger id is required'}, status=status.HTTP_400_BAD_REQUEST)
            trigger = get_object_or_404(StreamFilterTrigger, filter=obj, **request.data)
            trigger.delete()
            return Response(request.data, status=status.HTTP_204_NO_CONTENT)

    @action(methods=['post', 'delete'], detail=True)
    def action(self, request, slug=None):
        """
        POST: Create a new action.
        Fields:
        - type: (required) Str
        - extra_payload: (required) json str
        - entry_states: (optional) array of state ids that action will be put on entry
        - exit_states: (optional) array of state ids that action will be put on exit
        DELETE: Delete an action. on entry field or on exit field of any associated state will be set to None
        :param request:
        :param slug:
        :return:
        """
        obj = get_object_or_404(StreamFilter, slug=slug)
        if request.method == 'POST':
            serializer = StreamFilterActionSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(created_by=self.request.user)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        elif request.method == 'DELETE':
            if 'id' not in request.data:
                return Response({'error': 'Action id is required'}, status=status.HTTP_400_BAD_REQUEST)
            action = get_object_or_404(StreamFilterAction, id=request.data['id'])
            action.delete()
            return Response(request.data, status=status.HTTP_204_NO_CONTENT)
