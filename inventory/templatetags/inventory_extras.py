from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    if not mapping:
        return None
    return mapping.get(key)


@register.filter
def field_value(form, name):
    return form[name]


@register.filter
def percent(value, total):
    try:
        return round((float(value) / float(total)) * 100) if total else 0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0
