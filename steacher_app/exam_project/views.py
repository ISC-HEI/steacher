# Root-level views for the project
import re
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required


def is_mobile(request):
    """Detect if the request is from a mobile device."""
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    mobile_patterns = [
        r'android',
        r'iphone',
        r'ipad',
        r'ipod',
        r'blackberry',
        r'windows phone',
        r'mobile',
    ]
    return any(re.search(pattern, user_agent) for pattern in mobile_patterns)


def home(request):
    """
    Root view that redirects to mobile or desktop dashboard based on device.
    Handles both authenticated and unauthenticated users.
    """
    # If not authenticated, redirect to appropriate login
    if not request.user.is_authenticated:
        if is_mobile(request):
            return redirect('mobile:mobile_auth_request_link')
        else:
            return redirect('login')
    
    # If authenticated, redirect to appropriate dashboard
    if is_mobile(request):
        return redirect('mobile:mobile_dashboard')
    else:
        return redirect('exercises:dashboard')

