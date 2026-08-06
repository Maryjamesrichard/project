from django import template

from health_application.dynamic_translation import translate_dynamic


register = template.Library()


@register.filter(name="translate_dynamic")
def translate_dynamic_filter(value):
    """Translate human-readable database content into the active language."""
    return translate_dynamic(value)
