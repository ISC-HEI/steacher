# Sentry middleware for attaching user context to error reports
import sentry_sdk


class SentryContextMiddleware:
    """Attach user ID to Sentry events for better debugging."""
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            sentry_sdk.set_user({"id": request.user.id})
        
        response = self.get_response(request)
        return response
