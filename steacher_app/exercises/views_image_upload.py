import logging
import secrets
import base64
from io import BytesIO
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone
from django.urls import reverse

import qrcode
from PIL import Image

from .models import Trace, TraceImage
from .authz import rate_limit

logger = logging.getLogger(__name__)


def resize_and_convert_image(uploaded_file, max_width=2048, max_height=800):
    """
    Resize uploaded image, preserving original format when possible.
    Handles transparency, palette modes, and various image formats.
    Returns tuple of (image_bytes, content_type, file_size).
    """
    image_data = uploaded_file.read()
    
    # Pillow opens the image and detects what it is
    # SCENARIO: iPhone with "High Efficiency" → HEIC format
    #   - If Pillow can't read HEIC (no pillow-heif installed), this raises an exception
    #   - Exception gets caught by the view's try/except → returns error to user
    #   - In practice, modern browsers often convert HEIC to JPEG before upload
    # SCENARIO: iPhone camera in normal mode → JPEG (img.format='JPEG')
    # SCENARIO: Android screenshot → PNG (img.format='PNG')
    img = Image.open(BytesIO(image_data))
    
    # img.format tells us what Pillow detected: 'JPEG', 'PNG', 'HEIF', 'GIF', 'WEBP', etc. Always present, and in uppercase.
    original_format = img.format
    
    # img.mode tells us the color structure (how pixels are stored):
    # 'RGB' = regular color photo (red, green, blue channels) - most JPEG photos
    # 'RGBA' = color + transparency (red, green, blue, alpha) - PNG screenshots with transparency
    # 'L' = grayscale (luminance only) - black and white photos
    # 'P' = palette/indexed (uses color lookup table) - GIFs
    # 'CMYK' = print format - rare, from professional cameras
    
    # BRANCH 1: Handle images with transparency
    # Example: PNG screenshot with transparent background, stickers, etc.
    if img.mode == 'RGBA' or (img.mode == 'P' and 'transparency' in img.info):
        # We can't save transparency in JPEG, so we must use PNG
        if img.mode == 'P':
            # Convert palette with transparency to full RGBA for better quality
            img = img.convert('RGBA')
        output_format = 'PNG'
        content_type = 'image/png'
        
    # BRANCH 2: Normal images without transparency (most common path)
    # Example: iPhone photo, Android photo, screenshot without transparency
    elif img.mode in ('RGB', 'L'):
        # Check if the original format is something we want to preserve
        if original_format in ('JPEG', 'PNG'):
            # SCENARIO: iPhone camera photo (JPEG) → keep as JPEG (no quality loss)
            # SCENARIO: Android screenshot (PNG) → keep as PNG (text stays crisp)
            # This preserves quality: JPEG stays JPEG, PNG stays PNG
            output_format = original_format
            content_type = f'image/{original_format.lower()}'
        else:
            # SCENARIO: Unknown or exotic format (HEIC that Pillow decoded, WebP, BMP, etc.)
            # Convert to JPEG for maximum compatibility
            # Example: HEIC photo from iPhone → Pillow decoded it → img.format='HEIF' or None
            #          → we save as JPEG for universal compatibility
            output_format = 'JPEG'
            content_type = 'image/jpeg'
            
    # BRANCH 3: Weird color modes (rare)
    # Example: GIF without transparency, CMYK from professional camera, etc.
    else:
        # Convert to standard RGB and save as JPEG
        img = img.convert('RGB')
        output_format = 'JPEG'
        content_type = 'image/jpeg'
    
    # Resize if the image is too large (this is where we save disk space)
    # Example: iPhone 15 Pro photo is 4000x3000 pixels (12 megapixels)
    #          → thumbnail to 2048x1536 (3 megapixels)
    #          → file size drops from ~8MB to ~500KB
    # thumbnail() maintains aspect ratio: if it's 4000x3000, it becomes 2048x1536
    # If it's already smaller than 2048, nothing happens
    if img.width > max_width or img.height > max_height:
        img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
    
    # Save the processed image to bytes in memory
    output = BytesIO()
    if output_format == 'JPEG':
        # quality=85 means slight compression (100=max quality, 1=worst)
        # 85 is a sweet spot: looks great but much smaller than 100
        # optimize=True makes Pillow work harder to reduce file size
        img.save(output, format='JPEG', quality=85, optimize=True)
    else:
        # PNG: optimize=True compresses better without losing quality (PNG is lossless)
        img.save(output, format=output_format, optimize=True)
    resized_data = output.getvalue()
    
    return resized_data, content_type, len(resized_data)


@login_required
@require_POST
@rate_limit(user_limit=5, name='generate_upload_token')  # max 5 uploads per minute per user
def generate_upload_token(request):
    """Generate a short-lived upload token and TraceImage placeholder for the given attempt.
    Returns JSON with token, upload URL and a QR code data URI.
    """

    # generate a secure random token that expires in 10 minutes (hardcoded)
    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timedelta(minutes=10)

    try:
        # single placeholder row is created to track token and expiry. will be updated when the image is uploaded.
        TraceImage.objects.create(
            upload_token=token,
            token_expires_at=expires_at,
        )
    except Exception:
        logger.exception('Failed to create TraceImage token')
        return JsonResponse({'status': 'error', 'message': 'Failed to create upload token'}, status=500)

    upload_path = reverse('exercises:mobile_upload_page', args=[token])
    upload_url = request.build_absolute_uri(upload_path)

    try:
        qr = qrcode.make(upload_url)
        buf = BytesIO()
        qr.save(buf, format='PNG')
        qr_b64 = base64.b64encode(buf.getvalue()).decode('ascii')
        qr_data_uri = f'data:image/png;base64,{qr_b64}'
    except Exception:
        logger.exception('Failed to generate QR code')
        return JsonResponse({'status': 'error', 'message': 'Failed to generate QR code'}, status=500)

    return JsonResponse({
        'status': 'success',
        'token': token,
        'upload_url': upload_url,
        'expires_at': expires_at.isoformat(),
        'qr_code_data_uri': qr_data_uri,
    })


@require_GET
def mobile_upload_page(request, token):
    """
    Render the mobile upload page for the given token. 
    This is a public endpoint that is used on a mobile device, so no authentication is required.
    """
    image_record = TraceImage.objects.filter(upload_token=token).first()
    if not image_record:
        return HttpResponse('Invalid upload link', status=404)
    if not image_record.token_expires_at:
        return HttpResponse('Invalid upload link', status=404)
    if timezone.now() > image_record.token_expires_at:
        return HttpResponse('Upload link expired', status=403)

    # if already uploaded, show a simple message
    if image_record.image:
        return render(request, 'exercises/upload_already_used.html', status=400)

    return render(request, 'exercises/mobile_upload.html', {
        'token': token,
    })


@csrf_exempt
@require_POST
@rate_limit(ip_limit=10, name='mobile_upload_submit')
def mobile_upload_submit(request, token):
    """Handle the mobile image upload POST for the given token.
    This is a public endpoint that is used on a mobile device, so no authentication is required.
    Expects multipart/form-data with 'image' file field.
    """
    image_record = TraceImage.objects.filter(upload_token=token).first()
    if not image_record:
        return JsonResponse({'error': 'Invalid token'}, status=404)
    if not image_record.token_expires_at:
        return JsonResponse({'error': 'Invalid token'}, status=404)
    if timezone.now() > image_record.token_expires_at:
        return JsonResponse({'error': 'Token expired'}, status=403)

    if image_record.image:
        return JsonResponse({'error': 'Token already used'}, status=400)

    uploaded_file = request.FILES.get('image')
    if not uploaded_file:
        return JsonResponse({'error': 'No image provided'}, status=400)

    # basic validations
    if not uploaded_file.content_type.startswith('image/'):
        return JsonResponse({'error': 'Invalid file type'}, status=400)
    # 30MB should accommodate most smartphones
    if uploaded_file.size > 30 * 1024 * 1024:
        return JsonResponse({'error': 'File too large (max 30MB)'}, status=400)

    try:
        image_data, content_type, file_size = resize_and_convert_image(uploaded_file)
        
        image_record.image = image_data
        image_record.image_type = content_type
        image_record.file_size = file_size
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
    img = get_object_or_404(TraceImage, upload_token=token)
    
    if not img.image:
        return HttpResponse('No image', status=404)
    
    # Authorization: if linked to a trace, verify ownership or teacher status
    # If not yet linked, any logged-in user with the token can view it. This happens 
    # just for a short time, before the student sends the new message and creates a new trace.
    if img.trace:
        if img.trace.user != request.user and not request.user.is_teacher:
            return HttpResponse('Unauthorized', status=403)
    
    # Serve binary image data directly
    try:
        return HttpResponse(img.image, content_type=img.image_type)
    except Exception:
        logger.exception('Failed to serve image')
        return HttpResponse('Failed to serve image', status=500)


@login_required
@require_GET
def image_status(request, token):
    """Return upload status for a given upload token.
    Called by the desktop client polling for mobile upload completion.
    """
    img = TraceImage.objects.filter(upload_token=token).first()
    if not img:
        return JsonResponse({'status': 'error', 'message': 'Not found'}, status=404)
    
    if img.token_expires_at and timezone.now() > img.token_expires_at:
        return JsonResponse({'status': 'expired'}, status=403)
    
    if img.image:
        return JsonResponse({'status': 'completed'})
    return JsonResponse({'status': 'pending'})


