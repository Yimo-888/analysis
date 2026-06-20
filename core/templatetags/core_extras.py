from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Dict lookup by variable key: {{ d|get_item:k }}."""
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def sub(value, arg):
    """Subtraction: {{ a|sub:b }} → a - b."""
    try:
        return float(value) - float(arg)
    except (TypeError, ValueError):
        return ""
