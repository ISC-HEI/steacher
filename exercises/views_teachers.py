from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST
from django.db import transaction, models
import json

from .decorators import teacher_required
from .models import Exercise, Course, Module, ExerciceAsset
from .unit_testing import run_unit_tests
from .logic import generate_authoring_update


@login_required
@teacher_required
def course_list(request):
    courses = Course.objects.all()
    return render(request, 'exercises/teacher/teachers_course_list.html', {
        'courses': courses
    })


@login_required
@teacher_required
def course_detail(request, pk):
    course = get_object_or_404(Course.objects.prefetch_related('modules__exercises'), pk=pk)
    # Compute which exercises are completed by the current user for per-exercise checkmarks
    completed_ids = set()
    return render(request, 'exercises/teacher/teachers_course_details.html', {
        'course': course,
        'completed_exercise_ids': completed_ids,
    })


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

        course_ids = list(Module.objects.filter(id__in=module_ids).order_by().values_list('course_id', flat=True).distinct())
        if len(course_ids) != 1:
            return JsonResponse({'status': 'error', 'message': f"Modules must belong to a single course. Found: {course_ids}"}, status=400)

        course_id = course_ids[0]
        all_ids_in_course = list(Module.objects.filter(course_id=course_id).order_by('order').values_list('id', flat=True))
        ordered_ids = module_ids + [mid for mid in all_ids_in_course if mid not in module_ids]

        big_offset = 1000000
        temp_when = [models.When(id=mid, then=big_offset + idx) for idx, mid in enumerate(ordered_ids)]
        Module.objects.filter(id__in=ordered_ids).update(order=models.Case(*temp_when))
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

        module_ids = list(Exercise.objects.filter(id__in=exercise_ids).order_by().values_list('module_id', flat=True).distinct())
        if len(module_ids) != 1:
            return JsonResponse({'status': 'error', 'message': f"Exercises must belong to a single module. Found: {module_ids}"}, status=400)

        module_id = module_ids[0]
        all_ids_in_module = list(Exercise.objects.filter(module_id=module_id).order_by('order').values_list('id', flat=True))
        ordered_ids = exercise_ids + [eid for eid in all_ids_in_module if eid not in exercise_ids]

        big_offset = 1000000
        temp_when = [models.When(id=eid, then=big_offset + idx) for idx, eid in enumerate(ordered_ids)]
        Exercise.objects.filter(id__in=ordered_ids).update(order=models.Case(*temp_when))
        final_when = [models.When(id=eid, then=idx) for idx, eid in enumerate(ordered_ids)]
        Exercise.objects.filter(id__in=ordered_ids).update(order=models.Case(*final_when))

        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
@teacher_required
@require_POST
@transaction.atomic
def set_module_visibility(request, module_id):
    try:
        module = get_object_or_404(Module, pk=module_id)
        data = json.loads(request.body or '{}')
        visible = bool(data.get('visible'))

        module.visible = visible
        module.save(update_fields=['visible'])
        Module.objects.filter(pk=module.pk).update(updated_at=models.F('updated_at'))
        Exercise.objects.filter(module=module).update(visible=visible)

        return JsonResponse({
            'status': 'success',
            'module_id': module.id,
            'visible': module.visible,
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
@teacher_required
@require_POST
@transaction.atomic
def set_exercise_visibility(request, exercise_id):
    try:
        exercise = get_object_or_404(Exercise, pk=exercise_id)
        data = json.loads(request.body or '{}')
        visible = bool(data.get('visible'))
        exercise.visible = visible
        exercise.save(update_fields=['visible'])
        return JsonResponse({
            'status': 'success',
            'exercise_id': exercise.id,
            'visible': exercise.visible,
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
@teacher_required
def exercise_form(request, course_pk, exercise_pk=None):
    course = get_object_or_404(Course, pk=course_pk)

    if exercise_pk:
        exercise = get_object_or_404(Exercise, pk=exercise_pk, module__course=course)
    else:
        selected_module = course.modules.first()
        if not selected_module:
            return HttpResponse("Cannot add exercise: This course has no modules.", status=400)
        exercise = Exercise(
            module=selected_module,
            exercise_type='python',
            exercise_data={"question": ""},
            answer_data={"unit_tests": {"setup_code": "", "test_cases": [], "timeout_seconds": 5}},
        )

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            exercise.title = data.get('title', 'New Exercise')

            if not exercise.pk:
                with transaction.atomic():
                    Module.objects.select_for_update().get(pk=exercise.module_id)
                    max_order = (
                        Exercise.objects
                        .filter(module_id=exercise.module_id)
                        .aggregate(order__max=models.Max('order'))
                        .get('order__max')
                        or 0
                    )
                    exercise.order = max_order + 1

            exercise.description = data.get('description', '')
            exercise.exercise_type = data.get('exercise_type', 'python')
            exercise.exercise_data = data.get('exercise_data', {})
            answer_data = data.get('answer_data', {})
            if not answer_data:
                answer_data = {"unit_tests": {"setup_code": "", "test_cases": [], "timeout_seconds": 5}}
            exercise.answer_data = answer_data

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

    return render(request, 'exercises/teacher/exercise_form.html', {
        'course': course,
        'exercise': exercise,
        'exercise_json': exercise_json
    })


@login_required
@teacher_required
@require_POST
def exercise_authoring_assistant(request):
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


