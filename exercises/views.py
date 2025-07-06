from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.core import serializers
import json
from .models import Exercise, Answer, ExerciceAsset, Course
from .serializers import ExerciseSerializer, ExerciseFrontendSerializer, AnswerSerializer


def course_list(request):
    """Display list of all courses"""
    courses = Course.objects.all()
    return render(request, 'exercises/course_list.html', {
        'courses': courses
    })


def course_detail(request, pk):
    """Display individual course and its exercises"""
    course = get_object_or_404(Course, pk=pk)
    # Exercises are already ordered by the 'order' field in the model's Meta
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

    # Get user's previous answer if exists
    previous_answer = Answer.objects.filter(exercise=exercise).first()

    # Use public serializer to exclude answer_data from frontend
    exercise_json = ExerciseFrontendSerializer(exercise).data

    previous_answer_data = 'null'
    if previous_answer:
        previous_answer_data = AnswerSerializer(previous_answer).data
        previous_answer_data = json.dumps(previous_answer_data)

    # Choose template based on exercise type
    # LATER dynamically choose template based on exercise type
    if exercise.exercise_type == 'sql':
        template_name = 'exercises/sql.html'
    else:
        template_name = 'exercises/detail.html'

    return render(request, template_name, {
        'exercise': exercise,  # Pass the full exercise object for the template
        'exercise_json': exercise_json,  # Pass the JSON data for Vue/JS
        'previous_answer': previous_answer_data,
    })


def serve_asset(request, exercise_id, filename):
    """Serve asset files for exercises. Only serves assets relevant to the given exercise."""
    exercise = get_object_or_404(Exercise, pk=exercise_id)
    asset = get_object_or_404(ExerciceAsset, exercise=exercise, name=filename)

    # Convert memoryview to bytes, then decode to text
    content = bytes(asset.content).decode('utf-8')

    # Return as plain text with appropriate content type
    response = HttpResponse(content, content_type='text/plain')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response

