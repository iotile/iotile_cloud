
def _evaluate(value, operator, threshold):
    if operator == 'bu':
        return True

    if operator == 'eq':
        return value == threshold

    if operator == 'ne':
        return value != threshold

    if operator == 'le':
        return value <= threshold

    if operator == 'ge':
        return value >= threshold

    if operator == 'lt':
        return value < threshold

    if operator == 'gt':
        return value > threshold

    return False


def evaluate_trigger(trigger, value):

    operator = trigger.operator
    threshold = trigger.threshold
    return _evaluate(value, operator, threshold)


def evaluate_cached_trigger(trigger, value):
    operator = trigger['operator']
    threshold = trigger['threshold']
    return _evaluate(value, operator, threshold)


def evaluate_cached_transition(transition, value):
    for trigger in transition['triggers']:
        if not evaluate_cached_trigger(trigger, value):
            return False
    return True
