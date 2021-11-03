import logging

from django.conf import settings

from apps.streamfilter.models import StreamFilter
from apps.utils.data_helpers.manager import DataManager

from .actions.factory import action_factory
from .cache_utils import get_current_cached_filter_state_for_slug, set_current_cached_filter_state_for_slug
from .dynamodb import create_filter_log
from .processing.trigger import evaluate_cached_transition

# Get an instance of a logger
logger = logging.getLogger(__name__)


class FilterHelper(object):
    filter_dict = None
    derived_data = []
    skip_dynamo_logs = False

    def __init__(self, skip_dynamo_logs=False):
        self.skip_dynamo_logs = skip_dynamo_logs
        self.filter_dict = None
        self.derived_data = []

    def _create_derived_data(self):
        if len(self.derived_data) > 0:
            logger.info("Creating derived data")
            if getattr(settings, 'USE_FIREHOSE'):
                DataManager.send_to_firehose('data', self.derived_data)
            else:
                logger.debug('Using bulk-create (Production = {0})'.format(getattr(settings, 'PRODUCTION')))
                DataManager.bulk_create('data', self.derived_data)

    def _transition_should_execute(self, src, dst, current_state, transition, data):
        if src:
            # if the transition has a src and dst, then this transition should only be consider if the
            # transition src is the current state
            if current_state and src['slug'] != current_state:
                return False
        else:
            # If there is no src state, then only transition if current_state is different that dst state
            if current_state and current_state == dst['slug']:
                return False

        """
        If data is a StreamData instance, evaluate triggers of the transition
        If data is a StreamEventData instance, no value to evaluate, the transition is triggered in all case
        """
        if DataManager.is_instance('data', data):
            result = evaluate_cached_transition(transition, data.value)
            return result
        elif DataManager.is_instance('event', data):
            return True

    def _execute_action_if_needed(self, slug, transition, state, data, action_on, user_slug=None):
        if not state:
            return
        actions = state['actions']
        for action in actions:
            if action['on'] == action_on:
                action_obj = action_factory(action['type'])
                payload = {
                    'action': action,
                    'on': action_on,
                    'state': state,
                    'transition': transition,
                    'filter': slug,
                    'user_slug': user_slug,
                }
                logger.info('--> Processing FilterAction {}'.format(action_on))
                if action_obj.process(payload=payload, in_data=data):
                    logger.info('--> FilterAction {} has been executed'.format(action_on))
                    if action_obj.get_derived_stream_data():
                        self.derived_data.append(action_obj.get_derived_stream_data())

    def process_filter(self, data, cached_filter, user_slug=None):
        """
        :param data: 1 data point
        :param cached_filter: serialized and cached
        :return:
        """
        # 1.- Check if filter available for stream
        if cached_filter:
            states = cached_filter['states']
            states_map = {}
            for state in states:
                states_map[state['id']] = state
            for transition in cached_filter['transitions']:
                src = None
                assert transition['dst'] in states_map
                dst = states_map[transition['dst']]
                assert dst
                if 'src' in transition and transition['src'] and transition['src'] in states_map:
                    src = states_map[transition['src']]
                current_state = get_current_cached_filter_state_for_slug(data.stream_slug)

                if self._transition_should_execute(src, dst, current_state, transition, data):
                    if src and 'label' in src and src['label']:
                        src_label = src['label']
                    elif current_state:
                        src_label = current_state
                    else:
                        src_label = '*'
                    logger.info('--> Transition from {0} to {1}: {2}'.format(src_label, dst['slug'], data.stream_slug))
                    if not self.skip_dynamo_logs:
                        create_filter_log(
                            data.stream_slug, data.timestamp, src_label, dst['label'], transition['triggers']
                        )

                    # Execute any actions on state exit
                    if src:
                        self._execute_action_if_needed(
                            slug=cached_filter['slug'],
                            transition=transition,
                            state=src,
                            data=data,
                            action_on='exit',
                            user_slug=user_slug,
                        )
                    # Execute any actions on state entry
                    self._execute_action_if_needed(
                        slug=cached_filter['slug'],
                        transition=transition,
                        state=dst,
                        data=data,
                        action_on='entry',
                        user_slug=user_slug,
                    )

                    # Finally, Udate filter current state and log transition
                    set_current_cached_filter_state_for_slug(data.stream_slug, dst['slug'])

                    # Currentry only ever executing on transition, so if found, exit
                    return cached_filter

        return cached_filter

    def process_filter_report(self, entries, all_stream_filters, user_slug=None):
        # filter_dict contains only non null filters
        self.filter_dict = {}
        initial_states = {}
        for stream_slug, f in all_stream_filters.items():
            # if value:
            if 'empty' not in f:
                self.filter_dict[stream_slug] = f
                initial_states[f['slug']] = get_current_cached_filter_state_for_slug(stream_slug)
        if len(self.filter_dict) > 0:
            logger.info('{} filters found! Starting filter process...'.format(len(self.filter_dict)))
            for data in entries:
                # filters[data.stream_slug] isn't in filters if there is no filter for data.stream_slug
                if data.stream_slug in self.filter_dict:
                    self.process_filter(data, self.filter_dict[data.stream_slug], user_slug=user_slug)

            # TODO: Need to add a persistent record to store current_state (on top of redis copy)

            # Commit derived data
            self._create_derived_data()
