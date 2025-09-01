from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import csrf_protect
from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.db import models
from django.db.models import Prefetch
from django.utils import timezone
import json

from .models import Exercise, ExerciceAsset, Course, GuidanceLog, Trace, Module, StudentInvite, ChatThread
from .serializers import ExerciseFrontendSerializer


@login_required
def dashboard(request):
    """Student dashboard showing progress per course."""
    courses = Course.objects.filter(visible=True).prefetch_related('modules')

    course_progress = []
    for course in courses:
        total_exercises = Exercise.objects.filter(module__course=course, visible=True).count()
        completed_count = (
            Trace.objects.filter(
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

    return render(request, 'exercises/students/dashboard.html', {
        'course_progress': course_progress,
    })


@login_required
def course_list(request):
    """Display list of all courses for students (only visible ones)."""
    courses = Course.objects.filter(visible=True)
    return render(request, 'exercises/students/students_course_list.html', {
        'courses': courses
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

    invite = StudentInvite.objects.filter(email=email).first() if email else None
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
        Trace.objects.filter(user=request.user, complete=True, exercise__module__course=course)
        .values_list('exercise_id', flat=True)
    )

    visible_modules = (
        course.modules.filter(visible=True).order_by('order')
        .prefetch_related(Prefetch('exercises', queryset=Exercise.objects.filter(visible=True).order_by('order')))
    )

    return render(request, 'exercises/students/students_course_details.html', {
        'course': course,
        'modules': visible_modules,
        'completed_exercise_ids': completed_ids,
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
    exercise_json = ExerciseFrontendSerializer(exercise).data

    trace_id = None
    guidance_logs = []
    if request.user.is_authenticated:
        trace, _ = Trace.objects.get_or_create(user=request.user, exercise=exercise)
        trace_id = trace.id
        logs = GuidanceLog.objects.filter(trace=trace).order_by('submitted_at')
        guidance_logs = [log.interaction for log in logs]

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
        'multiple_choice': 'exercises/students/multiple_choice.html',
        'open_question': 'exercises/students/open_question.html',
    }
    template_name = template_map.get(exercise.exercise_type)
    if not template_name:
        raise Http404(f"Unsupported exercise type: {exercise.exercise_type}")

    return render(request, template_name, {
        'exercise': exercise,
        'exercise_json': exercise_json,
        'guidance_logs': guidance_logs,
        'trace_id': trace_id,
        'previous_exercise': previous_exercise,
        'next_exercise': next_exercise,
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
def get_guidance(request, exercise_id, trace_id):
    """
    Handles a user's request for guidance by calling the main guidance logic.
    """
    from .logic import fetch_ai_guidance  # local import to avoid circulars

    try:
        data = json.loads(request.body)
        exercise = get_object_or_404(Exercise, pk=exercise_id)
        trace = get_object_or_404(Trace, id=trace_id, exercise=exercise, user=request.user)

        response_data = fetch_ai_guidance(data, exercise, trace, debug=True)
        return JsonResponse({'status': 'success', **response_data})

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
    Deletes all GuidanceLog entries for the current user for a specific exercise.
    """
    exercise = get_object_or_404(Exercise, pk=exercise_id)
    Trace.objects.filter(user=request.user, exercise=exercise).delete()
    return redirect('exercises:exercise_detail', pk=exercise_id)



@login_required
def chat_home(request):
    """Render the simple AI chat page with the user's threads."""
    courses = Course.objects.filter(visible=True).order_by('name')
    # Default to last course from user's most recent trace
    last_trace = (
        Trace.objects.filter(user=request.user)
        .select_related('exercise__module__course')
        .order_by('-updated_at')
        .first()
    )
    default_course_id = None
    if last_trace and getattr(last_trace, 'exercise', None) and getattr(last_trace.exercise, 'module', None):
        default_course_id = last_trace.exercise.module.course.id
    return render(request, 'exercises/students/ai_chat.html', {
        'courses': courses,
        'default_course_id': default_course_id,
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
    return JsonResponse({
        'status': 'success',
        'thread': {
            'id': thread.id,
            'title': thread.title,
            'messages': thread.messages,
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

    # Prepare messages and append user message
    messages = list(thread.messages or [])
    now_iso = timezone.now().isoformat()
    messages.append({'role': 'user', 'content': user_text, 'created_at': now_iso})

    # Build AI prompt (study mode prompt + course context)
    from .logic import client, MODEL_NAME  # reuse existing configured client
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
            model=MODEL_NAME,
            messages=model_messages,
            temperature=0.6,
        )
        assistant_text = (completion.choices[0].message.content or '').strip()
    except Exception as e:
        assistant_text = f"Sorry, I couldn't reach the AI service. ({e})"

    messages.append({'role': 'assistant', 'content': assistant_text, 'created_at': timezone.now().isoformat()})
    # Trim stored history if it grows too large
    if len(messages) > 200:
        messages = messages[-200:]

    thread.messages = messages
    # Use first user line or assistant summary for title if default
    if thread.title == 'New Chat' and user_text:
        thread.title = (user_text.splitlines()[0] or 'New Chat')[:100]
    thread.save(update_fields=['messages', 'title', 'updated_at'])

    return JsonResponse({
        'status': 'success',
        'thread': {
            'id': thread.id,
            'title': thread.title,
            'messages': thread.messages,
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
