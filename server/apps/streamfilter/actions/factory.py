import logging

from apps.utils.dynamic_loading import str_to_class

from .action import BaseAction
from .eml_action.forms import EmailNotificationActionForm
from .slk_action.forms import SlackNotificationActionForm
from .cus_action.forms import CustomActionForm
from .drv_action.forms import DeriveStreamActionForm
from .sms_action.forms import SmsNotificationActionForm
from .rpt_action.forms import ReportActionForm
from .smry_action.forms import SummaryReportActionForm

logger = logging.getLogger(__name__)


FILTER_ACTION_FORMS = {
    'eml': EmailNotificationActionForm,
    'slk': SlackNotificationActionForm,
    'sms': SmsNotificationActionForm,
    'cus': CustomActionForm,
    'drv': DeriveStreamActionForm,
    'rpt': ReportActionForm,
    'smry': SummaryReportActionForm,
}


def action_form_class(type):
    if type in FILTER_ACTION_FORMS:
        return FILTER_ACTION_FORMS[type]
    return None


def action_factory(type):
    """
    Factory returns the proper Action object for the given type
    For any type, a TypeAction class should exist where <Type> is the capitalized
    string version of Type (e.g. for 'cnt', the class is 'CntAction')

    :param type: String representing type
    :return: Proper Action class
    """
    class_name = type.capitalize() + 'Action'
    module_name = '{0}.{1}_action.action'.format(__package__, type)
    logger.info('Looking for module {0}'.format(module_name))
    class_ = str_to_class(module_name, class_name)
    if class_:
        return class_()

    logger.error('****** action_factory failed to find class')
    return BaseAction()
