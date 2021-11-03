import logging

from .models import StreamNote, get_note_target_by_slug

# Get an instance of a logger
logger = logging.getLogger(__name__)


class StreamNoteBuilderHelper(object):
    _has_access = {}

    def __init__(self):
        self._has_access = {}

    def _build_stream_note(self, *args, **kwargs):
        note = StreamNote(**kwargs)
        return note

    def process_serializer_data(self, request, item):
        note = self._build_stream_note(**item)
        note.created_by = request.user
        return note

    def user_has_write_access(self, note, user):
        """
        Check if user has permission to create a note

        :param note: StreamNote object
        :param user: User object
        :return: True if user has access to target
        """
        target_slug = note.target_slug
        if target_slug in self._has_access:
            return self._has_access[target_slug]

        if target_slug not in self._has_access:
            target = get_note_target_by_slug(target_slug)
            self._has_access[target_slug] = target.has_access(user)

        return self._has_access[target_slug]
