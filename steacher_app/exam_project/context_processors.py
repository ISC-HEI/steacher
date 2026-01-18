# Context processors for making settings available in templates
from django.conf import settings


def sentry_context(request):
    """Make Sentry DSN and DEBUG available in templates."""
    return {
        'SENTRY_DSN': settings.SENTRY_DSN,
        'DEBUG': settings.DEBUG,
    }
