# Mobile-specific views for Steacher PWA
import logging
import secrets
from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, get_user_model
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.db.models import Max, Prefetch, Q
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

from groq import Groq

from .models import Exercise, Course, Module, Attempt, MobileAuthToken, localized_name, CohortMembership
from .authz import assert_can_view_exercise, rate_limit

logger = logging.getLogger(__name__)

# Lazy-initialize Groq client
def get_groq_client():
    """Get or create Groq client (lazy initialization)."""
    api_key = getattr(settings, 'GROQ_API_KEY', None)
    if not api_key:
        logger.error("Groq API key not configured (GROQ_API_KEY missing?)")
        return None
    return Groq(api_key=api_key)


@login_required
@require_GET
def mobile_install(request):
    """
    Installation instructions for adding Steacher as a PWA to home screen.
    """
    return render(request, 'exercises/mobile/mobile_install.html')


@login_required
@require_GET
def mobile_dashboard(request):
    """
    Mobile dashboard with recent exercises and hierarchical course/module/exercise view.
    """
    
    # Get courses where student has active cohort membership
    course_ids = list(
        CohortMembership.objects.filter(
            user=request.user,
            status='active'
        ).values_list('cohort__course', flat=True)
    )
    
    # Recent 5 exercises (open_question only)
    recent_attempts = (
        Attempt.objects.filter(
            user=request.user,
            exercise__module__course__id__in=course_ids,
            exercise__exercise_type='open_question'
        )
        .select_related('exercise__module__course')
        .order_by('-updated_at')[:5]
    )
    recent_exercises = []
    for att in recent_attempts:
        ex = att.exercise
        ex.localized_title = localized_name(ex, 'title_i18n', request.user)
        ex.is_complete = att.complete
        recent_exercises.append(ex)

    # Get last active exercise for "Continue where you left off" box
    last_exercise = recent_exercises[0] if len(recent_exercises) > 0 else None
    
    # Get all completed exercise IDs for this user
    completed_ids = set(
        Attempt.objects.filter(
            user=request.user,
            complete=True,
            exercise__module__course__id__in=course_ids
        ).values_list('exercise_id', flat=True)
    )
    
    # Sort courses by recent activity
    recent_attempts_by_course = (
        Attempt.objects.filter(user=request.user, exercise__module__course__id__in=course_ids)
        .values('exercise__module__course_id')
        .annotate(last_activity=Max('updated_at'))
    )
    last_attempt_map = {row['exercise__module__course_id']: row['last_activity'] for row in recent_attempts_by_course}
    
    # Fetch courses with modules and exercises
    courses = (
        Course.objects.filter(id__in=course_ids, visible=True)
        .prefetch_related(
            Prefetch(
                'modules',
                queryset=Module.objects.filter(visible=True).order_by('order').prefetch_related(
                    Prefetch(
                        'exercises',
                        queryset=Exercise.objects.filter(visible=True, exercise_type='open_question').order_by('order')
                    )
                )
            )
        )
    )
    
    # Build course data with progress
    course_data = []
    for course in courses:
        # Count total and completed exercises in this course
        all_exercise_ids = []
        modules_data = []
        
        for module in course.modules.filter(visible=True).order_by('order'):
            exercises_data = []
            module_exercise_ids = []
            
            for ex in module.exercises.filter(visible=True, exercise_type='open_question').order_by('order'):
                ex.localized_title = localized_name(ex, 'title_i18n', request.user)
                ex.is_complete = ex.id in completed_ids
                exercises_data.append(ex)
                module_exercise_ids.append(ex.id)
                all_exercise_ids.append(ex.id)
            
            # Module progress
            module_completed = sum(1 for eid in module_exercise_ids if eid in completed_ids)
            module_total = len(module_exercise_ids)
            
            modules_data.append({
                'module': module,
                'exercises': exercises_data,
                'completed': module_completed,
                'total': module_total,
            })
        
        # Course progress
        course_completed = sum(1 for eid in all_exercise_ids if eid in completed_ids)
        course_total = len(all_exercise_ids)
        
        course_data.append({
            'course': course,
            'modules': modules_data,
            'completed': course_completed,
            'total': course_total,
            'last_activity': last_attempt_map.get(course.id),
        })
    
    # Sort by recent activity
    course_data.sort(key=lambda x: (x['last_activity'] is not None, x['last_activity']), reverse=True)
    
    return render(request, 'exercises/mobile/mobile_dashboard.html', {
        'last_exercise': last_exercise,
        'recent_exercises': recent_exercises,
        'course_data': course_data,
    })


@login_required
@require_GET
def mobile_exercise(request, exercise_id):
    """
    Single-column mobile exercise interaction page.
    """
    exercise = get_object_or_404(Exercise, pk=exercise_id)
    assert_can_view_exercise(request.user, exercise)
    
    # Create or get attempt
    attempt, _ = Attempt.objects.get_or_create(user=request.user, exercise=exercise)
    
    # Get conversation history
    traces = attempt.traces.filter(channel='exercise_guidance').order_by('rank_order', 'id')
    
    interactions = []
    for tr in traces:
        # Extract guidance text from assistant_content (same as desktop view)
        guidance_text = ''
        if tr.assistant_content:
            if isinstance(tr.assistant_content, dict):
                guidance_text = tr.assistant_content.get('guidance_text', '') or ''
            else:
                # Fallback if it's stored as a string
                guidance_text = tr.assistant_content
        
        # Clean up user_content: remove LLM-specific prefixes for cleaner mobile display
        user_content = tr.user_content or ''
        # Strip legacy prefixes from old traces
        if user_content.startswith("Here is my submitted answer:"):
            user_content = user_content.replace("Here is my submitted answer:", "", 1).strip()
        if user_content.startswith("I have a specific question:"):
            user_content = user_content.replace("I have a specific question:", "", 1).strip()
        
        interactions.append({
            'user_submission': {
                'role': 'user',
                'content': user_content,
                'metadata': tr.user_metadata or {},
                'images': [{'image_token': img.upload_token} for img in tr.images.order_by('uploaded_at')],
            },
            'llm_response': {
                'role': 'assistant',
                'content': guidance_text,
                'trace_id': tr.id,
            },
        })
    
    # Localize exercise fields
    exercise_json = {
        'id': exercise.id,
        'title': localized_name(exercise, 'title_i18n', request.user),
        'description': localized_name(exercise, 'description_i18n', request.user),
        'question': localized_name(exercise, 'question_i18n', request.user),
        'exercise_type': exercise.exercise_type,
        'exercise_template': exercise.exercise_data_obj.answer_template,
    }
    
    # Convert interactions to JSON-safe format for Vue
    import json
    messages_for_vue = []
    logger.info(f"Processing {len(interactions)} interactions for mobile view")
    
    for idx, interaction in enumerate(interactions):
        logger.info(f"Interaction {idx}: user_content={interaction['user_submission']['content'][:50] if interaction['user_submission']['content'] else 'None'}")
        logger.info(f"Interaction {idx}: ai_content={interaction['llm_response']['content'][:50] if interaction['llm_response']['content'] else 'None'}")
        
        if interaction['user_submission']['content'] or interaction['user_submission']['images']:
            msg = {
                'role': 'user',
                'content': interaction['user_submission']['content'] or '',
            }
            if interaction['user_submission']['images']:
                msg['images'] = [
                    {'url': reverse('exercises:serve_trace_image', args=[img['image_token']])}
                    for img in interaction['user_submission']['images']
                ]
            messages_for_vue.append(msg)
            logger.info(f"Added user message: {msg['content'][:50]}")
        
        if interaction['llm_response']['content']:
            ai_msg = {
                'role': 'assistant',
                'content': interaction['llm_response']['content'],
            }
            messages_for_vue.append(ai_msg)
            logger.info(f"Added AI message: {ai_msg['content'][:50]}")
    
    logger.info(f"Total messages for Vue: {len(messages_for_vue)}")
    logger.info(f"Messages JSON: {json.dumps(messages_for_vue)[:200]}")
    
    # Get module and navigation context
    module = exercise.module
    module_exercises = list(module.exercises.filter(visible=True).order_by('order'))
    current_index = next((i for i, ex in enumerate(module_exercises) if ex.id == exercise.id), None)
    prev_exercise = module_exercises[current_index - 1] if current_index and current_index > 0 else None
    next_exercise = module_exercises[current_index + 1] if current_index is not None and current_index < len(module_exercises) - 1 else None
    
    # Get user's preferred language for speech recognition
    user_language = getattr(request.user, 'preferred_language', 'en')
    
    return render(request, 'exercises/mobile/mobile_exercise.html', {
        'exercise': exercise,
        'exercise_json': exercise_json,
        'attempt': attempt,
        'attempt_id': attempt.id,
        'interactions': interactions,
        'interactions_json': json.dumps(messages_for_vue),
        'transcribe_url': reverse('mobile:mobile_voice_transcribe'),
        'user_language': user_language,
        'module': module,
        'prev_exercise': prev_exercise,
        'next_exercise': next_exercise,
    })


@login_required
@require_POST
@rate_limit(user_limit=20, name='mobile_voice_transcribe')
def mobile_voice_transcribe(request):
    """
    Transcribe audio using Groq Whisper API.
    Returns transcribed text only (does not call AI tutor).
    """
    groq_client = get_groq_client()
    if not groq_client:
        logger.error("Groq client not configured (GROQ_API_KEY missing?)")
        return JsonResponse({'status': 'error', 'message': 'Voice transcription not configured'}, status=500)
    
    audio_file = request.FILES.get('audio')
    if not audio_file:
        logger.error("No audio file in request.FILES")
        return JsonResponse({'status': 'error', 'message': 'No audio file provided'}, status=400)
    
    logger.info(f"Received audio file: {audio_file.name}, size: {audio_file.size} bytes")

    # Get user's preferred language
    preferred_lang = getattr(request.user, 'preferred_language', 'en')
    logger.info(f"User preferred language: {preferred_lang}")
    
    # Map language codes to Whisper language parameter
    lang_map = {
        'en': 'en',
        'fr': 'fr',
        'de': 'de',
    }
    language = lang_map.get(preferred_lang, 'en')
    logger.info(f"Using Whisper language: {language}")
    
    try:
        # Call Groq Whisper API
        logger.info("Calling Groq Whisper API...")
        transcription = groq_client.audio.transcriptions.create(
            file=(audio_file.name, audio_file.read()),
            model="whisper-large-v3",
            language=language,
            temperature=0.0,
            response_format="json",
        )
        
        logger.info(f"Transcription success: {transcription.text[:50]}...")
        return JsonResponse({
            'status': 'success',
            'text': transcription.text,
        })
    
    except Exception as e:
        logger.exception(f"Error transcribing audio with Groq Whisper: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': f'Transcription failed: {str(e)}',
        }, status=500)


# Authentication endpoints (Magic Link Only)

@require_GET
def mobile_auth_request_link(request):
    """
    Show form to request magic link via email.
    """
    return render(request, 'exercises/mobile/mobile_auth_request.html')


@csrf_exempt
@require_POST
@rate_limit(ip_limit=10, name='mobile_auth_send_link')
def mobile_auth_send_link(request):
    """
    Send magic link to user's email.
    """
    email = (request.POST.get('email') or '').strip().lower()
    if not email:
        return JsonResponse({'status': 'error', 'message': 'Email is required'}, status=400)
    
    User = get_user_model()
    user = User.objects.filter(email=email).first()
    
    if not user:
        # Don't reveal if email exists (security best practice)
        return JsonResponse({'status': 'success', 'message': 'If that email exists, you will receive a login link.'})
    
    # Create token (9 bytes → 12 characters)
    token = secrets.token_urlsafe(9)
    
    validity_minutes = 30
    MobileAuthToken.objects.create(
        user=user,
        token=token,
        expires_at=timezone.now() + timedelta(minutes=validity_minutes)
    )
    magic_url = request.build_absolute_uri(reverse('mobile_magic_login', args=[token]))
    
    # Send email
    try:
        subject = 'Your Steacher Mobile Login Link'
        message = render_to_string('exercises/mobile/magic_link_email.txt', {
            'user': user,
            'magic_url': magic_url,
            'expires_minutes': validity_minutes,
        })
        
        logger.info(f"Sending magic link email to {email}")
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
        logger.info(f"Magic link email sent successfully to {email}")
        
    except Exception as e:
        logger.exception(f'Failed to send magic link email to {email}: {e}')
        # Return success anyway for security (don't reveal if email exists)
        # But log the error for debugging
        return JsonResponse({
            'status': 'success',
            'message': 'If that email exists, you will receive a login link. Note: Some university email servers may delay delivery by several minutes.'
        })
    
    return JsonResponse({
        'status': 'success',
        'message': 'Check your email for the login link. Note: Some university email servers may delay delivery.'
    })


@csrf_exempt
@require_GET
def mobile_magic_login(request, token):
    """
    Mobile endpoint: validate magic link token and create session.
    Allows reuse within 1 minute of first use to handle browser prefetching.
    """
    now = timezone.now()
    one_minute_ago = now - timedelta(minutes=1)
    
    # Find token that is either:
    # 1. Not used yet (used=False), OR
    # 2. First used within the last minute (first_used_at within 1 minute)
    auth_token = MobileAuthToken.objects.filter(
        token=token,
        expires_at__gt=now
    ).filter(
        Q(used=False) | Q(first_used_at__gt=one_minute_ago)
    ).select_related('user').first()
    
    if not auth_token:
        # If token is invalid but user is already logged in, just redirect to dashboard
        if request.user.is_authenticated:
            return redirect('mobile:mobile_dashboard')
        return HttpResponse('Invalid or expired login link. Please request a <a href="/">new login link</a>.', status=403)
    
    # Track first use or mark as fully used after 1 minute
    if auth_token.first_used_at is None:
        # First use: record timestamp but keep token reusable
        auth_token.first_used_at = now
        auth_token.save()
    elif auth_token.first_used_at <= one_minute_ago:
        # More than 1 minute since first use: mark as used
        auth_token.used = True
        auth_token.save()
    # Otherwise: within 1-minute window, allow reuse without updating
    
    # Create 6-month session
    login(request, auth_token.user, backend=settings.AUTHENTICATION_BACKENDS[0])
    request.session.set_expiry(60 * 60 * 24 * 180)  # 6 months
    request.session['is_mobile'] = True
    request.session['mobile_login_at'] = timezone.now().isoformat()
    
    # Redirect to original destination or dashboard
    next_url = request.GET.get('next', reverse('mobile:mobile_dashboard'))
    return redirect(next_url)

