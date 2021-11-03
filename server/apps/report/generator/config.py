

generator_configuration = {
    'default': {
        'sources_required': True,
        'required_config': ['cols']
    },
    'end_of_trip': {
        'sources_required': False,
        'required_config': []
    },
    'trip_update': {
        'sources_required': False,
        'required_config': []
    },
    'analytics': {
        'sources_required': False,
        'required_config': ['template']
    },
}


def rpt_configuration_requirements_met(generator, config, sources):
    if generator not in generator_configuration:
        return False

    if generator_configuration[generator]['sources_required']:
        if not sources:
            return False

    for key in generator_configuration[generator]['required_config']:
        if key not in config:
            return False
    return True
