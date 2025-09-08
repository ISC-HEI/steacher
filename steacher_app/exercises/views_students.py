from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import csrf_protect
from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.db import models
from django.db.models import Prefetch, Max
from django.utils import timezone
from datetime import timedelta
import requests
import time
import json

from .models import Exercise, ExerciceAsset, Course, Attempt, Module, UserInvite, ChatThread, CohortMembership, Trace, TraceEval, create_trace_for
from django.contrib.contenttypes.models import ContentType
from .serializers import ExerciseFrontendSerializer


def resolve_instructor_email(user, course=None):
    """Return the instructor email for the user's active cohort.

    Preference order:
    - If a course is provided, return the active membership instructor for that course.
    - Otherwise, return the most recent active membership instructor across any cohort.
    """
    from .models import CohortMembership, Cohort  # local import to avoid circulars on some setups

    try:
        membership = None
        # 1) Prefer membership for this course
        if course is not None:
            membership = (
                CohortMembership.objects
                .filter(user=user, status='active', cohort__course=course)
                .select_related('cohort')
                .order_by('-joined_at')
                .first()
            )
            if membership and getattr(membership.cohort.owner, 'email', ''):
                email = (membership.cohort.owner.email or '').strip()
                if email:
                    return email

            # 2) If user not enrolled, fall back to any cohort for this course
            any_course_cohort = (
                Cohort.objects
                .filter(course=course)
                .select_related()
                .order_by('-updated_at')
                .first()
            )
            if any_course_cohort and getattr(any_course_cohort.owner, 'email', ''):
                email = (any_course_cohort.owner.email or '').strip()
                if email:
                    return email

        # 3) Otherwise, use most recent active membership across any cohort
        membership = (
            CohortMembership.objects
            .filter(user=user, status='active')
            .select_related('cohort')
            .order_by('-joined_at')
            .first()
        )
        if membership and getattr(membership.cohort.owner, 'email', ''):
            email = (membership.cohort.owner.email or '').strip()
            if email:
                return email
    except Exception:
        pass
    return None

@login_required
def dashboard(request):
    """Student dashboard showing progress per course."""
    # Course progress (for compact list at the bottom)
    courses = Course.objects.filter(visible=True).order_by('name')

    course_progress = []
    for course in courses:
        total_exercises = Exercise.objects.filter(module__course=course, visible=True).count()
        completed_count = (
            Attempt.objects.filter(
                user=request.user,
                complete=True,
                exercise__module__course=course,
                exercise__visible=True,
            )
            .values('exercise_id')
            .distinct()
            .count()
        )
        percent = 0
        if total_exercises > 0:
            percent = int(round((completed_count / total_exercises) * 100))
        course_progress.append({
            'course': course,
            'completed': completed_count,
            'total': total_exercises,
            'percent': percent,
        })
    
    # Order courses by most recently interacted with (attempts or chats) for the current user
    # FIXME: only show courses where the student is part of a cohort.
    recent_attempts_by_course = (
        Attempt.objects
        .filter(user=request.user)
        .values('exercise__module__course_id')
        .annotate(last_activity=Max('updated_at'))
    )
    last_attempt_map = {row['exercise__module__course_id']: row['last_activity'] for row in recent_attempts_by_course}

    recent_chats_by_course = (
        ChatThread.objects
        .filter(owner=request.user)
        .values('course_id')
        .annotate(last_chat=Max('updated_at'))
    )
    last_chat_map = {row['course_id']: row['last_chat'] for row in recent_chats_by_course}

    def most_recent_ts(course_id):
        a = last_attempt_map.get(course_id)
        c = last_chat_map.get(course_id)
        if a and c:
            return a if a >= c else c
        return a or c  # may be None

    # Sort with most recently viewed first; items with no activity go last, original name order preserved among them
    course_progress.sort(key=lambda item: (
        most_recent_ts(item['course'].id) is not None,
        most_recent_ts(item['course'].id)
    ), reverse=True)
    
    # --- Primary Focus & Recents ---

    last_attempt = Attempt.objects.get_recent_for_user(request.user)
    last_active_exercise = last_attempt.exercise if last_attempt else None

    # Recent activity: last 7 attempts
    recent_attempts = Attempt.objects.get_recent_for_user(request.user, count=7)

    # Next up: next visible exercise after the most recently solved one in the same module
    next_up_exercise = None
    if last_active_exercise:
        module = last_active_exercise.module
        latest_solved = (
            Attempt.objects
            .filter(user=request.user, complete=True, exercise__module=module)
            .select_related('exercise')
            .order_by('-updated_at')
            .first()
        )
        base_order = latest_solved.exercise.order if latest_solved else None
        q = Exercise.objects.filter(module=module, visible=True)
        if base_order is not None:
            q = q.filter(order__gt=base_order)
        next_up_exercise = q.order_by('order').first()

    # Recent chats
    recent_chats = ChatThread.objects.filter(owner=request.user).order_by('-updated_at')[:7]

    # --- Quick Stats ---
    total_completed = Attempt.objects.filter(user=request.user, complete=True).values('exercise_id').distinct().count()
    
    # Calculate start of the current week (Monday morning)
    today = timezone.now().date()
    start_of_week = today - timedelta(days=today.weekday())

    week_completed = Attempt.objects.filter(
        user=request.user,
        complete=True,
        updated_at__gte=start_of_week
    ).values('exercise_id').distinct().count()

    module_stats = None
    if last_active_exercise:
        module = last_active_exercise.module
        module_total = Exercise.objects.filter(module=module, visible=True).count()
        module_completed = Attempt.objects.filter(
            user=request.user,
            complete=True,
            exercise__module=module
        ).values('exercise_id').distinct().count()
        if module_total > 0:
            module_stats = {
                "name": module.name,
                "completed": module_completed,
                "total": module_total,
            }

    # Localize titles for dashboard (primary focus + recent attempts)
    try:
        pref_lang = getattr(request.user, 'preferred_language', 'en') or 'en'
    except Exception:
        pref_lang = 'en'

    def pick_i18n(d: dict) -> str:
        if not isinstance(d, dict):
            return ''
        return d.get(pref_lang) or d.get('en') or next(iter(d.values()), '')

    try:
        if last_active_exercise:
            try:
                last_active_exercise.localized_title = pick_i18n(getattr(last_active_exercise, 'title_i18n', {}) or {})
            except Exception:
                last_active_exercise.localized_title = ''
        if next_up_exercise:
            try:
                next_up_exercise.localized_title = pick_i18n(getattr(next_up_exercise, 'title_i18n', {}) or {})
            except Exception:
                next_up_exercise.localized_title = ''
        for a in (recent_attempts or []):
            ex = getattr(a, 'exercise', None)
            if ex is not None:
                try:
                    ex.localized_title = pick_i18n(getattr(ex, 'title_i18n', {}) or {})
                except Exception:
                    ex.localized_title = ''
    except Exception:
        pass

    # Determine cohort instructor email to enable Teams button in navbar
    instructor_email = resolve_instructor_email(
        request.user,
        course=last_active_exercise.module.course if last_active_exercise else None,
    )

    return render(request, 'exercises/students/dashboard.html', {
        'course_progress': course_progress,
        'last_active_exercise': last_active_exercise,
        'recent_attempts': recent_attempts,
        'next_up_exercise': next_up_exercise,
        'recent_chats': recent_chats,
        'stats': {
            'total_completed': total_completed,
            'week_completed': week_completed,
            'module': module_stats,
        },
        'instructor_email': instructor_email,
    })


@login_required
def course_list(request):
    """Display list of all courses for students (only visible ones)."""
    courses = Course.objects.filter(visible=True)
    # Resolve instructor email from latest active cohort membership (any course)
    instructor_email = resolve_instructor_email(request.user)
    return render(request, 'exercises/students/students_course_list.html', {
        'courses': courses,
        'instructor_email': instructor_email,
    })


@csrf_protect
def register(request):
    if request.method == 'GET':
        return render(request, 'registration/register.html')

    email = (request.POST.get('email') or '').strip().lower()
    p1 = (request.POST.get('password1') or '').strip()
    p2 = (request.POST.get('password2') or '').strip()
    errors = []

    if not email:
        errors.append("Email is required.")
    if not p1 or not p2:
        errors.append("Both password fields are required.")
    if p1 != p2:
        errors.append("Passwords do not match.")

    invite = UserInvite.objects.filter(email=email).first() if email else None
    if not invite:
        errors.append("This email is not authorized to register.")
    elif invite.used:
        errors.append("This invite has already been used. Try logging in or resetting your password.")

    if errors:
        return render(request, 'registration/register.html', {'errors': errors, 'email': email})

    User = get_user_model()
    if User.objects.filter(username=email).exists():
        return render(request, 'registration/register.html', {
            'errors': ["An account with this email already exists. Use password reset if needed."], 'email': email
        })

    preferred_language = (request.POST.get('preferred_language') or 'en').strip()
    if preferred_language not in ['en', 'fr', 'de']:
        preferred_language = 'en'
    user = User.objects.create_user(username=email, email=email, password=p1)
    try:
        user.preferred_language = preferred_language
    except Exception:
        pass
    user.is_staff = False
    user.save()

    invite.mark_used(user)

    login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
    return redirect('exercises:dashboard')


@login_required
def course_detail(request, pk):
    """Display individual course and its visible modules/exercises for students."""
    course = get_object_or_404(Course.objects.prefetch_related('modules__exercises'), pk=pk, visible=True)

    # Compute which exercises are completed by the current user for per-exercise checkmarks
    completed_ids = set(
        Attempt.objects.filter(user=request.user, complete=True, exercise__module__course=course)
        .values_list('exercise_id', flat=True)
    )

    visible_modules = (
        course.modules.filter(visible=True).order_by('order')
        .prefetch_related(Prefetch('exercises', queryset=Exercise.objects.filter(visible=True).order_by('order')))
    )

    # Localize exercise titles/descriptions for listing
    try:
        pref_lang = getattr(request.user, 'preferred_language', 'en') or 'en'
    except Exception:
        pref_lang = 'en'

    def pick_i18n(d: dict) -> str:
        if not isinstance(d, dict):
            return ''
        return d.get(pref_lang) or d.get('en') or next(iter(d.values()), '')

    try:
        for module in visible_modules:
            ex_qs = getattr(module, 'exercises', None)
            if hasattr(ex_qs, 'all'):
                for ex in ex_qs.all():
                    try:
                        ex.localized_title = pick_i18n(getattr(ex, 'title_i18n', {}) or {})
                    except Exception:
                        ex.localized_title = ''
                    try:
                        ex.localized_description = pick_i18n(getattr(ex, 'description_i18n', {}) or {})
                    except Exception:
                        ex.localized_description = ''
    except Exception:
        pass

    return render(request, 'exercises/students/students_course_details.html', {
        'course': course,
        'modules': visible_modules,
        'completed_exercise_ids': completed_ids,
        'instructor_email': resolve_instructor_email(request.user, course=course),
    })


@login_required
def exercise_list(request):
    """Display list of all exercises (optional/student utility)."""
    exercises = Exercise.objects.all()
    return render(request, 'exercises/list.html', {
        'exercises': exercises
    })


@login_required
def exercise_detail(request, pk):
    """Display individual exercise for students."""
    exercise = get_object_or_404(Exercise, pk=pk)
    # Build localized exercise_json
    try:
        preferred_language = getattr(request.user, 'preferred_language', 'en') or 'en'
    except Exception:
        preferred_language = 'en'

    title_map = getattr(exercise, 'title_i18n', {}) or {}
    desc_map = getattr(exercise, 'description_i18n', {}) or {}
    def pick(d: dict) -> str:
        if not isinstance(d, dict):
            return ''
        return d.get(preferred_language) or d.get('en') or next(iter(d.values()), '')

    ex_data = dict(exercise.exercise_data or {})
    q_map = getattr(exercise, 'question_i18n', {}) or {}
    if isinstance(q_map, dict):
        question_text = q_map.get(preferred_language) or q_map.get('en') or next(iter(q_map.values()), '')
    else:
        question_text = ''

    exercise_json = {
        'id': exercise.id,
        'title': pick(title_map),
        'description': pick(desc_map),
        'question': question_text,
        'exercise_type': exercise.exercise_type,
        'exercise_data': ex_data,
        'created_at': exercise.created_at.isoformat(),
        'updated_at': exercise.updated_at.isoformat(),
    }
    localized_title = exercise_json['title']
    localized_description = exercise_json['description']

    attempt_id = None
    interactions = []
    attempt = None
    completion_feedback = None
    if request.user.is_authenticated:
        attempt, _ = Attempt.objects.get_or_create(user=request.user, exercise=exercise)
        attempt_id = attempt.id
        if attempt.completion_feedback:
            completion_feedback = attempt.completion_feedback
        # Map traces to shape expected by frontend
        attempt_ct = ContentType.objects.get_for_model(Attempt, for_concrete_model=False)
        traces = (
            Trace.objects
            .filter(content_type=attempt_ct, object_id=attempt.id, channel='exercise_guidance')
            .order_by('rank_order', 'id')
        )
        interactions = []
        for tr in traces:
            interactions.append({
                'user_submission': {
                    'role': 'user',
                    'content': tr.user_content or '',
                    'metadata': tr.user_metadata or {},
                },
                'llm_response': {
                    'role': 'assistant',
                    'content': tr.assistant_content or '',
                    'trace_id': tr.id,
                    'metadata': tr.assistant_metadata or {},
                },
            })

    # Determine neighbors within the same module by order
    previous_exercise = (
        Exercise.objects
        .filter(module=exercise.module, order__lt=exercise.order)
        .order_by('-order')
        .first()
    )
    next_exercise = (
        Exercise.objects
        .filter(module=exercise.module, order__gt=exercise.order)
        .order_by('order')
        .first()
    )

    template_map = {
        'sql': 'exercises/students/sql.html',
        'python': 'exercises/students/python.html',
        'scala': 'exercises/students/scala.html',
        'open_question': 'exercises/students/open_question.html',
    }
    template_name = template_map.get(exercise.exercise_type)
    if not template_name:
        raise Http404(f"Unsupported exercise type: {exercise.exercise_type}")

    # Determine cohort instructor email for this course, if any
    instructor_email = resolve_instructor_email(request.user, course=exercise.module.course)

    return render(request, template_name, {
        'exercise': exercise,
        'exercise_json': exercise_json,
        'interactions': interactions,
        'attempt_id': attempt_id,
        'attempt': attempt,
        'completion_feedback': completion_feedback,
        'previous_exercise': previous_exercise,
        'next_exercise': next_exercise,
        'instructor_email': instructor_email,
        'localized_title': localized_title,
        'localized_description': localized_description,
    })


@login_required
def serve_asset(request, exercise_id, filename):
    """Serve asset files for exercises."""
    exercise = get_object_or_404(Exercise, pk=exercise_id)
    asset = get_object_or_404(ExerciceAsset, course=exercise.module.course, name=filename)
    content = bytes(asset.content).decode('utf-8')
    response = HttpResponse(content, content_type='text/plain')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@login_required
@require_POST
def get_guidance(request, exercise_id, attempt_id):
    """
    Handles a user's request for guidance by calling the main guidance logic.
    """
    from .logic import fetch_ai_guidance  # local import to avoid circulars
    from pydantic import ValidationError

    try:
        data = json.loads(request.body)
        exercise = get_object_or_404(Exercise, pk=exercise_id)
        attempt = get_object_or_404(Attempt, id=attempt_id, exercise=exercise, user=request.user)

        response_data = fetch_ai_guidance(data, exercise, attempt, debug=True)
        return JsonResponse({'status': 'success', **response_data})

    except ValidationError as e:
        return JsonResponse({
            'status': 'error',
            'message': f"Exercise data is incompatible with the current format. Please ask a teacher to update this exercise. Details: {e}"
        }, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    except ValueError as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    except Exception as e:
        print(f"An error occurred in get_guidance: {e}")
        return JsonResponse({'status': 'error', 'message': 'An internal error occurred.'}, status=500)


@login_required
def delete_user_answers(request, exercise_id):
    """
    Deletes all traces for the current user's attempt for a specific exercise.
    """
    exercise = get_object_or_404(Exercise, pk=exercise_id)
    Attempt.objects.filter(user=request.user, exercise=exercise).delete()
    return redirect('exercises:exercise_detail', pk=exercise_id)



@login_required
@require_POST
def scala_execute(request):
    """Proxy Scala code execution to the scala_interpreter service."""
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    code = (payload.get('code') or '').strip()
    if not code:
        return JsonResponse({'success': False, 'output': '', 'error': 'No code provided'}, status=400)

    url = f"{getattr(settings, 'SCALA_INTERPRETER_URL', 'http://scala_interpreter:8642')}/execute"
    start = time.time()
    try:
        resp = requests.post(url, json={'code': code}, timeout=20)
        duration_ms = int((time.time() - start) * 1000)
        resp.raise_for_status()
        data = resp.json() or {}
        # Normalize response
        return JsonResponse({
            'success': bool(data.get('success')),
            'output': str(data.get('output') or ''),
            'error': str(data.get('error') or '') if data.get('error') else None,
            'durationMs': duration_ms,
        })
    except requests.exceptions.RequestException as e:
        duration_ms = int((time.time() - start) * 1000)
        return JsonResponse({'success': False, 'output': '', 'error': f'Request failed: {e}', 'durationMs': duration_ms}, status=502)


@login_required
def chat_home(request):
    """Render the simple AI chat page with the user's threads."""
    courses = Course.objects.filter(visible=True).order_by('name')
    # Stupid simple default: pick the highest ChatThread id for this user
    default_course_id = None
    default_thread_id = None
    try:
        last_thread = ChatThread.objects.filter(owner=request.user).order_by('-id').first()
    except Exception:
        last_thread = None
    if last_thread is not None:
        default_thread_id = last_thread.id
        default_course_id = last_thread.course_id
    else:
        # Fallback to last course from user's most recent attempt
        last_attempt = Attempt.objects.get_recent_for_user(request.user)
        if last_attempt and getattr(last_attempt, 'exercise', None) and getattr(last_attempt.exercise, 'module', None):
            default_course_id = last_attempt.exercise.module.course.id
    return render(request, 'exercises/students/ai_chat.html', {
        'courses': courses,
        'default_course_id': default_course_id,
        'default_thread_id': default_thread_id,
    })


@login_required
def chat_threads(request):
    """
    GET: return list of threads for the current user
    POST: create a new thread and return it
    """
    if request.method == 'GET':
        course_id = request.GET.get('course_id')
        if not course_id:
            return JsonResponse({'status': 'error', 'message': 'course_id is required'}, status=400)
        try:
            course = Course.objects.get(id=int(course_id), visible=True)
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Invalid course_id'}, status=400)
        threads = ChatThread.objects.filter(owner=request.user, course=course).order_by('-updated_at')
        data = [
            {
                'id': t.id,
                'title': t.title,
                'course_id': t.course_id,
                'course_name': t.course.name,
                'updated_at': t.updated_at.isoformat(),
                'created_at': t.created_at.isoformat(),
            }
            for t in threads
        ]
        return JsonResponse({'status': 'success', 'threads': data})

    if request.method == 'POST':
        try:
            payload = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

        course_id = payload.get('course_id')
        if not course_id:
            return JsonResponse({'status': 'error', 'message': 'course_id is required'}, status=400)
        try:
            course = Course.objects.get(id=int(course_id), visible=True)
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Invalid course_id'}, status=400)

        title = (payload.get('title') or '').strip() or 'New Chat'
        thread = ChatThread.objects.create(owner=request.user, course=course, title=title, messages=[])
        return JsonResponse({
            'status': 'success',
            'thread': {
                'id': thread.id,
                'title': thread.title,
                'course_id': thread.course_id,
                'course_name': thread.course.name,
                'updated_at': thread.updated_at.isoformat(),
                'created_at': thread.created_at.isoformat(),
            }
        })

    return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)


@login_required
def chat_thread_detail(request, thread_id: int):
    """Return a single thread with messages (JSON)."""
    thread = get_object_or_404(ChatThread, id=thread_id, owner=request.user)
    # Rebuild messages from Trace
    thread_ct = ContentType.objects.get_for_model(ChatThread, for_concrete_model=False)
    traces = (
        Trace.objects
        .filter(content_type=thread_ct, object_id=thread.id, channel='study_chat')
        .order_by('rank_order', 'id')
    )
    messages = []
    for tr in traces:
        if (tr.user_content or '').strip():
            messages.append({'role': 'user', 'content': tr.user_content, 'created_at': tr.created_at.isoformat()})
        if (tr.assistant_content or '').strip():
            messages.append({'role': 'assistant', 'content': tr.assistant_content, 'trace_id': tr.id, 'created_at': tr.created_at.isoformat()})
    return JsonResponse({
        'status': 'success',
        'thread': {
            'id': thread.id,
            'title': thread.title,
            'messages': messages,
            'course_id': thread.course_id,
            'course_name': thread.course.name,
            'updated_at': thread.updated_at.isoformat(),
            'created_at': thread.created_at.isoformat(),
        }
    })


@login_required
@require_POST
def chat_thread_send(request, thread_id: int):
    """
    Append a user message, call the AI, append assistant reply, and return updated messages.
    """
    thread = get_object_or_404(ChatThread, id=thread_id, owner=request.user)
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    user_text_raw = (payload.get('message') or '').strip()
    if not user_text_raw:
        return JsonResponse({'status': 'error', 'message': 'Message is required'}, status=400)

    # Basic limits
    user_text = user_text_raw[:4000]

    # Prepare context messages reconstructed from Trace
    thread_ct = ContentType.objects.get_for_model(ChatThread, for_concrete_model=False)
    existing_traces = (
        Trace.objects
        .filter(content_type=thread_ct, object_id=thread.id, channel='study_chat')
        .order_by('rank_order', 'id')
    )
    # Use the entire conversation history
    messages = []
    for tr in existing_traces:
        if (tr.user_content or '').strip():
            messages.append({'role': 'user', 'content': tr.user_content})
        if (tr.assistant_content or '').strip():
            messages.append({'role': 'assistant', 'content': tr.assistant_content})
    # Append current user message
    messages.append({'role': 'user', 'content': user_text})

    # Build AI prompt (study mode prompt + course context)
    from .logic import client, MODEL_FAST  # reuse existing configured client
    with open('exercises/study_mode_prompt.md', 'r') as file:
        base_prompt = file.read()

    course = thread.course
    course_context = ''
    try:
        if (course.chat_prompt or '').strip():
            course_context = course.chat_prompt.strip()
        elif (course.description or '').strip():
            desc = course.description.strip()
            course_context = desc[:1000]
    except Exception:
        course_context = ''

    system_prompt = base_prompt
    if course_context:
        system_prompt = f"{base_prompt}\n\nCONTEXT FOR THIS COURSE: {course.name}\n{course_context}"

    model_messages = [{'role': 'system', 'content': system_prompt}]
    # Cap context to the last ~40 messages to control token usage
    tail = messages[-40:]
    for m in tail:
        role = 'user' if m.get('role') == 'user' else 'assistant'
        content = str(m.get('content') or '')
        model_messages.append({'role': role, 'content': content})

    try:
        completion = client.chat.completions.create(
            model=MODEL_FAST,
            messages=model_messages,
            temperature=0.6,
        )
        assistant_text = (completion.choices[0].message.content or '').strip()
    except Exception as e:
        assistant_text = f"Sorry, I couldn't reach the AI service. ({e})"

    # Persist as Trace(s) in study_chat channel, storing full message pair
    # First study_chat trace?
    is_first = not Trace.objects.filter(content_type=thread_ct, object_id=thread.id, channel__in=['study_chat', 'exercise_guidance']).exists()
    fields = {
        'user_content': user_text,
        'assistant_content': assistant_text,
        'assistant_metadata': {
            'assistant_message': assistant_text,
        },
    }
    if is_first:
        fields['system_prompt'] = system_prompt
    created = create_trace_for(thread, request.user, channel='study_chat', **fields)

    # Use first user line or assistant summary for title if default
    if thread.title == 'New Chat' and user_text:
        thread.title = (user_text.splitlines()[0] or 'New Chat')[:100]
    thread.save(update_fields=['title', 'updated_at'])

    return JsonResponse({
        'status': 'success',
        'thread': {
            'id': thread.id,
            'title': thread.title,
            'messages': [{'role': 'user', 'content': user_text, 'created_at': timezone.now().isoformat()},
                         {'role': 'assistant', 'content': assistant_text, 'trace_id': getattr(created, 'id', None), 'created_at': timezone.now().isoformat()}],
            'updated_at': thread.updated_at.isoformat(),
            'created_at': thread.created_at.isoformat(),
        }
    })


@login_required
@require_POST
def chat_thread_delete(request, thread_id: int):
    """Delete a thread owned by the user."""
    thread = get_object_or_404(ChatThread, id=thread_id, owner=request.user)
    thread.delete()
    return JsonResponse({'status': 'success'})


@login_required
@require_POST
def recommend_learning_pathway(request, attempt_id):
    """
    Analyzes a completed attempt and returns personalized feedback and next-step recommendations.
    """
    from .logic import generate_learning_pathway_recommendation

    try:
        attempt = get_object_or_404(Attempt, id=attempt_id, user=request.user)
        if not attempt.complete:
            return JsonResponse({'status': 'error', 'message': 'Attempt is not marked as complete.'}, status=400)

        # Re-fetch interactions from the DB to ensure we have the canonical, untampered history
        # as the single source of truth, rather than trusting client-side state.
        attempt_ct = ContentType.objects.get_for_model(Attempt, for_concrete_model=False)
        traces = (
            Trace.objects
            .filter(content_type=attempt_ct, object_id=attempt.id, channel='exercise_guidance')
            .order_by('rank_order', 'id')
        )
        interactions = [
            {
                'user_submission': {
                    'role': 'user',
                    'content': tr.user_content or '',
                    'metadata': tr.user_metadata or {},
                },
                'llm_response': {
                    'role': 'assistant',
                    'content': tr.assistant_content or '',
                    'metadata': tr.assistant_metadata or {},
                },
            }
            for tr in traces
        ]

        # Call the core logic function to get the recommendation from the LLM
        recommendation_data = generate_learning_pathway_recommendation(
            attempt=attempt,
            interactions=interactions
        )

        if "error" in recommendation_data:
            return JsonResponse({'status': 'error', 'message': recommendation_data.get('details', 'Failed to get recommendation.')}, status=500)

        # Persist the recommendation as a Trace in the learning_pathway channel (and keep existing field for now)
        try:
            attempt_ct = ContentType.objects.get_for_model(Attempt, for_concrete_model=False)
            # Determine if this is the first pathway trace; if so, store a minimal system prompt marker
            has_any_pathway = Trace.objects.filter(content_type=attempt_ct, object_id=attempt.id, channel='learning_pathway').exists()
            lp_fields = {
                'user_content': 'request_learning_pathway',
                'assistant_content': 'learning_pathway_recommendation',
                'assistant_metadata': {
                    'learning_pathway': recommendation_data,
                },
            }
            if not has_any_pathway:
                lp_fields['system_prompt'] = 'Learning pathway recommender system prompt (implicit)'
            create_trace_for(attempt, request.user, channel='learning_pathway', **lp_fields)
        except Exception:
            pass

        # Also persist the recommendation in the attempt for backward compatibility
        attempt.completion_feedback = recommendation_data
        attempt.save(update_fields=['completion_feedback'])

        return JsonResponse({'status': 'success', 'data': recommendation_data})

    except Attempt.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Attempt not found.'}, status=404)
    except Exception as e:
        print(f"An error occurred in recommend_learning_pathway: {e}")
        return JsonResponse({'status': 'error', 'message': 'An internal error occurred.'}, status=500)


@login_required
@require_POST
def trace_eval_create(request):
    """Create a TraceEval row from { trace_id, result } with minimal validation.
    result: "ok" | "not_ok". Feedback empty. Ensure trace belongs to current user.
    """
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    trace_id = payload.get('trace_id')
    result = (payload.get('result') or '').strip().lower()
    if not trace_id or result not in ('ok', 'not_ok'):
        return JsonResponse({'status': 'error', 'message': 'trace_id and valid result are required'}, status=400)

    try:
        trace = Trace.objects.select_related('user').get(id=int(trace_id))
    except Exception:
        return JsonResponse({'status': 'error', 'message': 'Trace not found'}, status=404)

    # Basic ownership check
    if getattr(trace, 'user_id', None) != getattr(request.user, 'id', None):
        return JsonResponse({'status': 'error', 'message': 'Forbidden'}, status=403)

    is_ok = True if result == 'ok' else False
    te = TraceEval.objects.create(trace=trace, is_ok=is_ok, feedback='')
    return JsonResponse({'status': 'success', 'id': te.id, 'trace_id': trace.id, 'is_ok': te.is_ok}, status=201)
