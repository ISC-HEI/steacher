from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.core import serializers
import json
from .models import Exercise, Answer
from .serializers import ExerciseSerializer, AnswerSerializer


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
    
    # Serialize data using Django REST Framework serializers
    exercise_data = ExerciseSerializer(exercise).data
    
    previous_answer_data = 'null'
    if previous_answer:
        previous_answer_data = AnswerSerializer(previous_answer).data
        previous_answer_data = json.dumps(previous_answer_data)
    
    return render(request, 'exercises/detail.html', {
        'exercise': json.dumps(exercise_data),
        'previous_answer': previous_answer_data,
    })


@method_decorator(csrf_exempt, name='dispatch')
class SubmitAnswerView(View):
    def post(self, request, pk):
        """Handle answer submission"""
        exercise = get_object_or_404(Exercise, pk=pk)
        
        try:
            data = json.loads(request.body)
            user_answer = data.get('answer')
            
            # Calculate if answer is correct (for multiple choice)
            is_correct = None
            if exercise.exercise_type == 'multiple_choice':
                correct_choice = None
                for choice in exercise.exercise_data.get('choices', []):
                    if choice.get('is_correct', False):
                        correct_choice = choice['id']
                        break
                is_correct = user_answer == correct_choice
            
            # Save the answer
            answer = Answer.objects.create(
                exercise=exercise,
                user_answer=user_answer,
                is_correct=is_correct
            )
            
            return JsonResponse({
                'success': True,
                'is_correct': is_correct,
                'message': 'Answer submitted successfully!'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
