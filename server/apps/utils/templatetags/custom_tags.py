from django import template

register = template.Library()

@register.filter
def get_item(obj, key):
    """
    Use as dict|get_item:key
    """
    if key in obj:
        return obj[key]
    return ''
