import importlib
import logging

logger = logging.getLogger(__name__)

def str_to_class(module_name, class_name):
    try:
        module_ = importlib.import_module(module_name)
        try:
            class_ = getattr(module_, class_name)
        except AttributeError as e:
            logging.error('Class does not exist')
            raise e
    except ImportError as e:
        logging.error('Module does not exist', str(e))
        raise e
    return class_


