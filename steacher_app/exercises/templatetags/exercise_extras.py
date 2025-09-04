from django import template

register = template.Library()


@register.filter
def exercise_code(exercise):
    """
    Return a short code like "M1.E3" for a given Exercise instance based on
    the module and exercise order (1-based). Falls back gracefully if data
    is missing.
    """
    try:
        module = getattr(exercise, 'module', None)
        if module is None:
            return ''

        module_index = (getattr(module, 'order', None) or 0) + 1
        exercise_index = (getattr(exercise, 'order', None) or 0) + 1

        if module_index <= 0 or exercise_index <= 0:
            return ''

        return f"M{module_index}.E{exercise_index}"
    except Exception:
        return ''


