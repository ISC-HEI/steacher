from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
import json
from openai import OpenAI

from .logic import fetch_ai_guidance
from .models import Exercise, ExerciceAsset, Course, GuidanceLog, Trace
from .serializers import ExerciseSerializer, ExerciseFrontendSerializer


client = OpenAI(api_key=settings.OPENAI_API_KEY)


def course_list(request):
    """Display list of all courses"""
    courses = Course.objects.all()
    return render(request, 'exercises/course_list.html', {
        'courses': courses
    })


def course_detail(request, pk):
    """Display individual course and its exercises"""
    course = get_object_or_404(Course, pk=pk)
    exercises = course.exercises.all()
    return render(request, 'exercises/course_detail.html', {
        'course': course,
        'exercises': exercises
    })


def exercise_list(request):
    """Display list of all exercises"""
    exercises = Exercise.objects.all()
    return render(request, 'exercises/list.html', {
        'exercises': exercises
    })


def exercise_detail(request, pk):
    """Display individual exercise"""
    exercise = get_object_or_404(Exercise, pk=pk)
    exercise_json = ExerciseFrontendSerializer(exercise).data

    trace_id = None
    guidance_logs = []
    if request.user.is_authenticated:
        trace, _ = Trace.objects.get_or_create(user=request.user, exercise=exercise)
        trace_id = trace.id
        logs = GuidanceLog.objects.filter(trace=trace).order_by('submitted_at')
        guidance_logs = [log.interaction for log in logs]

    template_map = {
        'sql': 'exercises/sql.html',
        'python': 'exercises/python.html',
        'multiple_choice': 'exercises/multiple_choice.html'
    }
    template_name = template_map.get(exercise.exercise_type, 'exercises/detail.html')

    return render(request, template_name, {
        'exercise': exercise,
        'exercise_json': exercise_json,
        'guidance_logs': guidance_logs,
        'trace_id': trace_id,
    })


def serve_asset(request, exercise_id, filename):
    """Serve asset files for exercises."""
    exercise = get_object_or_404(Exercise, pk=exercise_id)
    asset = get_object_or_404(ExerciceAsset, exercise=exercise, name=filename)
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
    try:
        data = json.loads(request.body)
        exercise = get_object_or_404(Exercise, pk=exercise_id)
        trace = get_object_or_404(Trace, id=trace_id, exercise=exercise, user=request.user)

        response_data = fetch_ai_guidance(data, exercise, trace)
        
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
