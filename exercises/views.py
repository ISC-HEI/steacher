from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.db import transaction, models
import json
from openai import OpenAI

from .logic import fetch_ai_guidance, generate_authoring_update
from .models import Exercise, ExerciceAsset, Course, GuidanceLog, Trace, Module
from .serializers import ExerciseSerializer, ExerciseFrontendSerializer
from .decorators import teacher_required
from .unit_testing import run_unit_tests


client = OpenAI(api_key=settings.OPENAI_API_KEY)

@login_required
def course_list(request):
    """Display list of all courses"""
    courses = Course.objects.all()
    return render(request, 'exercises/course_list.html', {
        'courses': courses
    })

@login_required
def course_detail(request, pk):
    """Display individual course and its exercises"""
    course = get_object_or_404(Course.objects.prefetch_related('modules__exercises'), pk=pk)
    return render(request, 'exercises/course_detail.html', {
        'course': course,
    })

@login_required
def exercise_list(request):
    """Display list of all exercises"""
    exercises = Exercise.objects.all()
    return render(request, 'exercises/list.html', {
        'exercises': exercises
    })


@login_required
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
@teacher_required
def exercise_form(request, course_pk, exercise_pk=None):
    course = get_object_or_404(Course, pk=course_pk)
    
    if exercise_pk:
        exercise = get_object_or_404(Exercise, pk=exercise_pk, module__course=course)
    else:
        # Provide a default structure for a new exercise
        # For now, assign it to the first module of the course.
        # This could be improved with a module selector in the UI.
        first_module = course.modules.first()
        if not first_module:
            # Handle case where a course has no modules yet
            # You might want to create a default module or redirect with an error.
            # For now, we'll just prevent creation.
            return HttpResponse("Cannot add exercise: This course has no modules.", status=400)

        exercise = Exercise(
            module=first_module,
            exercise_type='python',
            exercise_data={
                "question": "",
            },
            answer_data={
                "unit_tests": {
                    "setup_code": "",
                    "test_cases": [],
                    "timeout_seconds": 5
                }
            }
        )

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            exercise.title = data.get('title', 'New Exercise')
            
            if not exercise.pk:  # This is a new exercise
                max_order = exercise.module.exercises.aggregate(models.Max('order'))['order__max'] or 0
                exercise.order = max_order + 1
            else:
                exercise.order = data.get('order', exercise.order) # Keep existing order on edit

            exercise.description = data.get('description', '')
            exercise.exercise_type = data.get('exercise_type', 'python')
            exercise.exercise_data = data.get('exercise_data', {})
            
            # TODO: Add logic to change module if needed from the form data
            
            answer_data = data.get('answer_data', {})
            if not answer_data:
                 answer_data = {
                    "unit_tests": {
                        "setup_code": "# Setup code (e.g., imports) runs before student's code.",
                        "test_cases": [],
                        "timeout_seconds": 5
                    }
                }
            exercise.answer_data = answer_data

            # Validate SQL DB asset selection when relevant
            if exercise.exercise_type == 'sql':
                db_name = (exercise.exercise_data or {}).get('db')
                if db_name:
                    valid_assets = set(
                        ExerciceAsset.objects.filter(course=course, name__iendswith='.sql')
                        .values_list('name', flat=True)
                    )
                    if db_name not in valid_assets:
                        return JsonResponse({
                            'status': 'error',
                            'message': f"Selected database '{db_name}' is not an available SQL asset for this course."
                        }, status=400)

            # Validate correct answers against unit tests
            if exercise.exercise_type == 'python' and 'unit_tests' in answer_data:
                unit_tests = answer_data.get('unit_tests', {})
                correct_answers = answer_data.get('correct_answers', [])
                for i, correct_answer in enumerate(correct_answers):
                    code_to_test = correct_answer.get('answer', '')
                    test_results = run_unit_tests(code_to_test, unit_tests)
                    if not test_results.get('all_passed'):
                        failed_tests = [res for res in test_results['test_results'] if not res['passed']]
                        error_message = f"Correct Answer #{i+1} failed {len(failed_tests)} unit test(s). Please fix the answer or the tests."
                        return JsonResponse({'status': 'error', 'message': error_message, 'details': failed_tests}, status=400)

            exercise.save()
            return JsonResponse({'status': 'success', 'exercise_pk': exercise.pk})
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    # Serialize the exercise data to pass to the Vue app
    # Compute available SQL assets for this course
    available_sql_assets = list(
        ExerciceAsset.objects.filter(course=course, name__iendswith='.sql')
        .values_list('name', flat=True)
    )

    exercise_json = {
        "pk": exercise.pk,
        "title": exercise.title,
        "order": exercise.order,
        "description": exercise.description,
        "exercise_type": exercise.exercise_type,
        "exercise_data": exercise.exercise_data,
        "answer_data": exercise.answer_data,
        "available_sql_assets": available_sql_assets,
        "course_pk": course.pk,
    }

    return render(request, 'exercises/exercise_form.html', {
        'course': course,
        'exercise': exercise,
        'exercise_json': exercise_json
    })


@login_required
@teacher_required
@require_POST
def exercise_authoring_assistant(request):
    """
    Stateless endpoint used by the in-page authoring assistant.
    Does not persist conversation; returns assistant text and updated exercise DTO.
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    exercise_payload = body.get('exercise') or {}
    messages = body.get('messages') or []
    context = body.get('context') or {}
    course_pk = context.get('course_pk')

    if not isinstance(messages, list):
        return JsonResponse({'status': 'error', 'message': 'messages must be a list'}, status=400)

    if not course_pk:
        return JsonResponse({'status': 'error', 'message': 'Missing course_pk in context'}, status=400)

    course = get_object_or_404(Course, pk=course_pk)

    try:
        result = generate_authoring_update(exercise_payload=exercise_payload, messages=messages, course=course)
        return JsonResponse({'status': 'success', **result})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
@teacher_required
@require_POST
@transaction.atomic
def reorder_modules(request):
    try:
        data = json.loads(request.body)
        module_ids = [int(mid) for mid in data.get('module_ids', [])]
        if not module_ids:
            return JsonResponse({'status': 'error', 'message': 'No module_ids provided'}, status=400)

        # Determine the course these modules belong to.
        # We must clear the default model ordering with .order_by() before calling .distinct()
        # to prevent the ordering fields from making each row unique.
        course_ids = list(Module.objects.filter(id__in=module_ids).order_by().values_list('course_id', flat=True).distinct())
        if len(course_ids) != 1:
            return JsonResponse({'status': 'error', 'message': f"Modules must belong to a single course. Found: {course_ids}"}, status=400)
        course_id = course_ids[0]

        # Reorder ALL modules in the course to avoid conflicts with untouched rows.
        all_ids_in_course = list(Module.objects.filter(course_id=course_id).order_by('order').values_list('id', flat=True))
        # Keep incoming order for provided ids, append any missing ids preserving relative order.
        ordered_ids = module_ids + [mid for mid in all_ids_in_course if mid not in module_ids]

        # Two-phase update to avoid unique (course, order) clashes mid-update.
        # Phase 1: move to a high, disjoint range
        big_offset = 1000000
        temp_when = [models.When(id=mid, then=big_offset + idx) for idx, mid in enumerate(ordered_ids)]
        Module.objects.filter(id__in=ordered_ids).update(order=models.Case(*temp_when))
        # Phase 2: set to final contiguous order starting at 0
        final_when = [models.When(id=mid, then=idx) for idx, mid in enumerate(ordered_ids)]
        Module.objects.filter(id__in=ordered_ids).update(order=models.Case(*final_when))

        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
@teacher_required
@require_POST
@transaction.atomic
def reorder_exercises(request):
    try:
        data = json.loads(request.body)
        exercise_ids = [int(eid) for eid in data.get('exercise_ids', [])]
        if not exercise_ids:
            return JsonResponse({'status': 'error', 'message': 'No exercise_ids provided'}, status=400)

        # Determine the module these exercises belong to.
        # We must clear the default model ordering with .order_by() before calling .distinct()
        # to prevent the ordering fields from making each row unique.
        module_ids = list(Exercise.objects.filter(id__in=exercise_ids).order_by().values_list('module_id', flat=True).distinct())
        if len(module_ids) != 1:
            return JsonResponse({'status': 'error', 'message': f"Exercises must belong to a single module. Found: {module_ids}"}, status=400)
        module_id = module_ids[0]

        # Reorder ALL exercises in the module to avoid conflicts with untouched rows.
        all_ids_in_module = list(Exercise.objects.filter(module_id=module_id).order_by('order').values_list('id', flat=True))
        # Keep incoming order for provided ids, append any missing ids preserving relative order.
        ordered_ids = exercise_ids + [eid for eid in all_ids_in_module if eid not in exercise_ids]

        # Two-phase update to avoid unique (module, order) clashes mid-update.
        # Phase 1: move to a high, disjoint range
        big_offset = 1000000
        temp_when = [models.When(id=eid, then=big_offset + idx) for idx, eid in enumerate(ordered_ids)]
        Exercise.objects.filter(id__in=ordered_ids).update(order=models.Case(*temp_when))
        # Phase 2: set to final contiguous order starting at 0
        final_when = [models.When(id=eid, then=idx) for idx, eid in enumerate(ordered_ids)]
        Exercise.objects.filter(id__in=ordered_ids).update(order=models.Case(*final_when))

        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
