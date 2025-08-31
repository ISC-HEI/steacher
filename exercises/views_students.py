from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.db import models
from django.db.models import Prefetch
import json

from .models import Exercise, ExerciceAsset, Course, GuidanceLog, Trace, Module
from .serializers import ExerciseFrontendSerializer


@login_required
def course_list(request):
    """Display list of all courses for students (only visible ones)."""
    courses = Course.objects.filter(visible=True)
    return render(request, 'exercises/students/students_course_list.html', {
        'courses': courses
    })


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


