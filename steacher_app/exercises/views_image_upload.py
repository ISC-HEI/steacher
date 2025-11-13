from django.conf import settings
import logging
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse, FileResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone
from datetime import timedelta
import secrets
import base64
from django.urls import reverse

from .models import Trace

logger = logging.getLogger(__name__)



@login_required
@require_POST
def generate_upload_token(request, trace_id):
    """Generate a short-lived upload token and TraceImage placeholder for the given attempt.
    Returns JSON with token and upload URL; optionally a QR code data URI if qrcode is installed.
    """
    trace = get_object_or_404(Trace, pk=trace_id, user=request.user)
    #exercise = attempt.exercise

    # Rate limiting could be applied here using rate_limit decorator if desired
    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timedelta(minutes=30)

    img = None
    try:
        # Single placeholder row created to track token and expiry
        from .models import TraceImage
        img = TraceImage.objects.create(
            trace=trace,
            upload_token=token,
            token_expires_at=expires_at,
        )
    except Exception:
        logger.exception('Failed to create TraceImage token')
        return JsonResponse({'status': 'error', 'message': 'Failed to create upload token'}, status=500)

    upload_path = reverse('exercises:mobile_upload_page', args=[token])
    upload_url = request.build_absolute_uri(upload_path)

    qr_data_uri = None
    try:
        import qrcode
        from io import BytesIO
        qr = qrcode.make(upload_url)
        buf = BytesIO()
        qr.save(buf, format='PNG')
        qr_b64 = base64.b64encode(buf.getvalue()).decode('ascii')
        qr_data_uri = f'data:image/png;base64,{qr_b64}'
    except Exception:
        # QR generation optional; continue without it
        qr_data_uri = None

    return JsonResponse({
        'status': 'success',
        'token': token,
        'upload_url': upload_url,
        'expires_at': expires_at.isoformat(),
        'qr_code_data_uri': qr_data_uri,
    })


@require_GET
def mobile_upload_page(request, token):
    """Render the mobile upload page for the given token (no authentication required).
    """
    from .models import TraceImage
    image_record = TraceImage.objects.filter(upload_token=token).first()
    if not image_record:
        return HttpResponse('Invalid upload link', status=404)

    if timezone.now() > image_record.token_expires_at:
        return HttpResponse('Upload link expired', status=403)

    # If already uploaded, show a simple message
    if image_record.image:
        return render(request, 'exercises/upload_already_used.html', status=400)

    return render(request, 'exercises/mobile_upload.html', {
        'token': token,
    })


@csrf_exempt
@require_POST
def mobile_upload_submit(request, token):
    """Handle the mobile image upload POST for the given token (no auth required).
    Expects multipart/form-data with 'image' file field.
    """
    from .models import TraceImage
    image_record = TraceImage.objects.filter(upload_token=token).first()
    if not image_record:
        return JsonResponse({'error': 'Invalid token'}, status=404)

    if timezone.now() > image_record.token_expires_at:
        return JsonResponse({'error': 'Token expired'}, status=403)

    if image_record.image:
        return JsonResponse({'error': 'Token already used'}, status=400)

    uploaded_file = request.FILES.get('image')
    if not uploaded_file:
        return JsonResponse({'error': 'No image provided'}, status=400)

    # Basic validations
    if not uploaded_file.content_type.startswith('image/'):
        return JsonResponse({'error': 'Invalid file type'}, status=400)
    if uploaded_file.size > 5 * 1024 * 1024:
        return JsonResponse({'error': 'File too large (max 5MB)'}, status=400)

    try:
        # Store the uploaded file as binary data
        image_data = uploaded_file.read()
        
        image_record.image = image_data
        image_record.image_type = uploaded_file.content_type
        image_record.file_size = uploaded_file.size
        image_record.uploaded_at = timezone.now()
        image_record.save()
        return JsonResponse({'status': 'success'})
    except Exception:
        logger.exception('Failed to save uploaded image')
        return JsonResponse({'error': 'Upload failed'}, status=500)


@login_required
@require_GET
def serve_trace_image(request, token):
    """Serve a trace image using its upload token."""
    from .models import TraceImage
    img = get_object_or_404(TraceImage, upload_token=token)
    if not img.image:
        return HttpResponse('No image', status=404)
    # Serve binary image data directly
    try:
        return HttpResponse(img.image, content_type=img.image_type)
    except Exception:
        logger.exception('Failed to serve image')
        return HttpResponse('Failed to serve image', status=500)


def serve_qr_code(request, token):
    """Generate and serve a QR code for the mobile upload page."""
    upload_url = request.build_absolute_uri(reverse('exercises:mobile_upload_page', args=[token]))
    
    try:
        import qrcode
        from io import BytesIO
        qr = qrcode.make(upload_url)
        buf = BytesIO()
        qr.save(buf, format='PNG')
        buf.seek(0)
        return FileResponse(buf, content_type='image/png')
    except Exception:
        return HttpResponse('Failed to generate QR code', status=500)


@require_GET
def image_status(request, token):
    """Return upload status for a given upload token (unauthenticated polling endpoint)."""
    from .models import TraceImage
    img = TraceImage.objects.filter(upload_token=token).first()
    if not img:
        return JsonResponse({'status': 'error', 'message': 'Not found'}, status=404)
    # Expired
    try:
        if img.token_expires_at and timezone.now() > img.token_expires_at:
            return JsonResponse({'status': 'expired'}, status=403)
    except Exception:
        pass
    if img.image:
        return JsonResponse({'status': 'completed'})
    return JsonResponse({'status': 'pending'})


@login_required
@require_POST
def delete_trace_image(request, trace_id, image_id):
    trace = get_object_or_404(Trace, pk=trace_id, user=request.user)
    from .models import TraceImage
    img = get_object_or_404(TraceImage, pk=image_id, trace=trace)
    img.delete()
    return JsonResponse({'status': 'success'})
