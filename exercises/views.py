from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
import json
from openai import OpenAI

from .models import Exercise, ExerciceAsset, Course, GuidanceLog
from .serializers import ExerciseSerializer, ExerciseFrontendSerializer


# Initialize OpenAI client
client = OpenAI(api_key=settings.OPENAI_API_KEY)


def calculate_cbm_score(selections, correct_answer_ids, all_choices):
    """
    Calculates the score for a multiple-choice question using Certainty-Based Marking.
    """
    score_matrix = {
        'right': {'correct': 2, 'incorrect': -2},
        'wrong': {'correct': -1, 'incorrect': 1},
        'notsure': {'correct': 0, 'incorrect': 0}
    }

    results = {}
    total_score = 0
    max_score = 0

    # Get all choice IDs from the exercise data
    all_choice_ids = [choice['id'] for choice in all_choices]

    for choice_id in all_choice_ids:
        student_confidence = selections.get(choice_id)
        is_correct_option = choice_id in correct_answer_ids

        # Calculate the maximum possible score for this option
        max_score += score_matrix['right']['correct'] if is_correct_option else score_matrix['wrong']['incorrect']

        if not student_confidence:
            # This case should ideally be prevented by frontend validation
            score = 0
            actual_status = 'missing'
        else:
            # Determine if the student's confidence matches the option's status
            status_key = 'correct' if is_correct_option else 'incorrect'
            score = score_matrix[student_confidence][status_key]
        
        results[choice_id] = {
            'student_confidence': student_confidence,
            'actual_status': 'correct' if is_correct_option else 'wrong',
            'score': score
        }
        total_score += score

    return {
        'total_score': total_score,
        'max_score': max_score,
        'breakdown': results
    }


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

    # Use public serializer to exclude answer_data from frontend
    exercise_json = ExerciseFrontendSerializer(exercise).data

    # Fetch the full conversation history for the user on this exercise
    guidance_logs = []
    if request.user.is_authenticated:
        logs = GuidanceLog.objects.filter(exercise=exercise, user=request.user).order_by('submitted_at')
        # We'll just pass the 'interaction' part of each log to the frontend
        guidance_logs = [log.interaction for log in logs]

    # Choose template based on exercise type TODO make this dynamic
    if exercise.exercise_type == 'sql':
        template_name = 'exercises/sql.html'
    elif exercise.exercise_type == 'python':
        template_name = 'exercises/python.html'
    elif exercise.exercise_type == 'multiple_choice':
        template_name = 'exercises/multiple_choice.html'
    else:
        template_name = 'exercises/detail.html'

    return render(request, template_name, {
        'exercise': exercise,  # Pass the full exercise object for the template
        'exercise_json': exercise_json,  # Pass the JSON data for Vue/JS
        'guidance_logs': guidance_logs,
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


@login_required
@require_POST
def get_guidance(request, exercise_id):
    """
    Handles a user's request for guidance, sends it to the LLM,
    and stores the interaction.
    """
    try:
        data = json.loads(request.body)
        exercise = get_object_or_404(Exercise, pk=exercise_id)
        
        # 1. Construct the user's message for the LLM
        user_prompt_content = ""
        action = data.get('action')

        if action == 'ask_question':
            user_prompt_content = f"I have a specific question: {data.get('question', '')}"
        elif action == 'ask_hint':
            user_prompt_content = "I am explicitly asking for a hint."
        elif action == 'submit_answer' and exercise.exercise_type == 'multiple_choice':
            selections = data.get('selections', {})
            justification = data.get('justification', '')
            correct_answers = exercise.answer_data.get('correct_answers', [])
            all_choices = exercise.exercise_data.get('choices', [])
            
            # Calculate score
            cbm_result = calculate_cbm_score(selections, correct_answers, all_choices)
            
            # Format the results for the LLM prompt
            score_breakdown = "\n".join(
                [
                    f"- **Option {choice_id.upper()}:** I chose '{result['student_confidence']}'; the correct answer is: {result['actual_status']}. **Score: {result['score']}**"
                    for choice_id, result in cbm_result['breakdown'].items()
                ]
            )
            
            user_prompt_content = (
                f"Here are my answers:\n"
                f"{score_breakdown}\n\n"
                f"**Total Score: {cbm_result['total_score']} / {cbm_result['max_score']} points.**"
            )

            if justification:
                user_prompt_content += f"\n\nMy justification was:\n{justification}"
            else:
                user_prompt_content += "\n\nI did not provide a justification."

        elif action == 'run_query':
            user_prompt_content = f"I ran this SQL query:\n```sql\n{data.get('code', '')}\n```\n"
            if data.get('error_message'):
                user_prompt_content += f"But I got an error:\n```\n{data.get('error_message')}\n```"
            else:
                user_prompt_content += f"And I got this result:\n```\n{data.get('query_result')}\n```"
        elif action == 'run_code':
            user_prompt_content = f"I ran this Python code:\n```python\n{data.get('code', '')}\n```\n"
            if data.get('error_message'):
                user_prompt_content += f"But I got an error:\n```\n{data.get('error_message')}\n```"
            else:
                user_prompt_content += f"And I got this result:\n```\n{data.get('output')}\n```"
        elif action == 'submit_answer' and exercise.exercise_type != 'multiple_choice':
            user_prompt_content = f"I chose the answer '{data.get('answer')}'."
            if data.get('justification'):
                user_prompt_content += f"\nMy justification is:\n{data.get('justification')}"
            else:
                user_prompt_content += "\nI did not provide a justification."
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid action'}, status=400)

        # 2. Fetch conversation history
        guidance_logs = GuidanceLog.objects.filter(exercise=exercise, user=request.user)
        messages = []

        # 3. Add system prompt
        # read General Prompt 
        with open('exercises/general_prompt.md', 'r') as file:
            system_prompt = file.read()
        # add prompt from Course
        course_prompt = exercise.course.llm_prompts.get(exercise.exercise_type)
        if course_prompt:
            system_prompt += f"\n\n{course_prompt}"
        # add prompt from Exercise
        exercise_answer_data = exercise.answer_data
        if exercise_answer_data:
            # add expected result
            system_prompt += f"\n\nExpected result: {exercise_answer_data.get('expected_result')}"
            # add correct answers
            system_prompt += f"\n\nCorrect answers: {exercise_answer_data.get('correct_answers')}"
            # add hints
            system_prompt += f"\n\nHints that can be provided to help the student: {exercise_answer_data.get('hints')}"
            # add additional context
            system_prompt += f"\n\nAdditional context for this exercise: {exercise_answer_data.get('additional_context')}"
        
        # Add correct choice for multiple choice questions
        if exercise.exercise_type == 'multiple_choice':
            system_prompt += f"\n\nExplanations for each choice are: {exercise_answer_data.get('choice_explanations')}"


        messages.append({"role": "system", "content": system_prompt})

        # 4. Add past messages from the log
        for log in guidance_logs:
            messages.append(log.interaction['user_submission'])
            if 'llm_response' in log.interaction and log.interaction['llm_response']:
                messages.append(log.interaction['llm_response'])

        # 5. Add the current user message
        user_submission = {
            "role": "user",
            "content": user_prompt_content
        }
        messages.append(user_submission)

        # log the messages
        print(f"Messages: {messages}")

        # 6. Call the OpenAI API
        llm_response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        assistant_content = llm_response.choices[0].message.content.strip()

        # 7. Create the log entry
        interaction_log = {
            "user_submission": {
                "role": "user",
                "content": user_prompt_content,
                "metadata": data  # Store all the raw data from the frontend
            },
            "llm_response": {
                "role": "assistant",
                "content": assistant_content,
                "metadata": {
                    "model": llm_response.model,
                    "usage": {
                        "completion_tokens": llm_response.usage.completion_tokens,
                        "prompt_tokens": llm_response.usage.prompt_tokens,
                        "total_tokens": llm_response.usage.total_tokens,
                    },
                    "finish_reason": llm_response.choices[0].finish_reason
                }
            }
        }
        
        # For CBM, add the scoring breakdown to the log's submission metadata
        if action == 'submit_answer' and exercise.exercise_type == 'multiple_choice':
            interaction_log['user_submission']['metadata']['cbm_result'] = cbm_result

        GuidanceLog.objects.create(
            exercise=exercise,
            user=request.user,
            interaction=interaction_log
        )

        # 8. Return the guidance to the frontend
        response_data = {
            'status': 'success',
            'guidance': assistant_content,
            'user_submission': interaction_log['user_submission']
        }
        
        # For CBM, also return the scoring breakdown so the frontend can display it
        if action == 'submit_answer' and exercise.exercise_type == 'multiple_choice':
            response_data['cbm_result'] = cbm_result
            
        return JsonResponse(response_data)

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        # Log the exception for debugging
        print(f"An error occurred in get_guidance: {e}")
        return JsonResponse({'status': 'error', 'message': 'An internal error occurred.'}, status=500)


@login_required
def delete_user_answers(request, exercise_id):
    """
    Deletes all GuidanceLog entries for the current user for a specific exercise. Mostly useful for debugging.
    """
    exercise = get_object_or_404(Exercise, pk=exercise_id)
    GuidanceLog.objects.filter(user=request.user, exercise=exercise).delete()
    return redirect('exercises:exercise_detail', pk=exercise_id)

