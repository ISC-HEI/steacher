# Middleware to automatically trust ngrok origins for CSRF in DEBUG mode
import re
from django.conf import settings


class NgrokCSRFMiddleware:
    """
    Automatically add ngrok origins to CSRF_TRUSTED_ORIGINS in DEBUG mode.
    This allows ngrok testing without modifying settings each time.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if settings.DEBUG:
            host = request.get_host()
            # Check if this is an ngrok domain
            if re.match(r'^[\w-]+\.ngrok(-free)?\.app$', host) or re.match(r'^[\w-]+\.ngrok\.io$', host):
                origin = f'https://{host}'
                if origin not in settings.CSRF_TRUSTED_ORIGINS:
                    settings.CSRF_TRUSTED_ORIGINS.append(origin)
        
        response = self.get_response(request)
        return response

