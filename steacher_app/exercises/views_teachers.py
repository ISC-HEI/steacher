from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST
from django.db import transaction, models
import json

from .decorators import teacher_required
from .models import Exercise, Course, Module, ExerciceAsset, Cohort, CohortMembership, Attempt, AttemptInteraction
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
    # Remember last visited course for teacher dashboard defaulting
    try:
        request.session['last_teacher_course_id'] = course.id
    except Exception:
        pass
    # Compute which exercises are completed by the current user for per-exercise checkmarks
    completed_ids = set()
    return render(request, 'exercises/teacher/teachers_course_details.html', {
        'course': course,
        'completed_exercise_ids': completed_ids,
    })


@login_required
@teacher_required
def dashboard(request):
    """Teacher dashboard: cohort-scoped student progress and activity."""
    # 1) Resolve default cohort
    cohort_qs = Cohort.objects.filter(owner=request.user).select_related('course')
    selected_cohort = None

    # Try explicit GET param first
    cohort_id = request.GET.get('cohort')
    if cohort_id:
        selected_cohort = cohort_qs.filter(id=cohort_id).first()

    if not selected_cohort:
        # Try last teacher course from session
        course_id = request.session.get('last_teacher_course_id')
        if course_id:
            selected_cohort = cohort_qs.filter(course_id=course_id).order_by('-updated_at', '-id').first()

    if not selected_cohort:
        # Fallback to most recently updated owned cohort
        selected_cohort = cohort_qs.order_by('-updated_at', '-id').first()

    students_data = []
    histogram = []  # per number of completed exercises -> list of student names
    max_bar_count = 0

    if selected_cohort:
        course = selected_cohort.course
        ordered_exercises = list(
            Exercise.objects
            .filter(module__course=course, visible=True)
            .select_related('module')
            .order_by('module__order', 'order')
        )
        total_exercises = len(ordered_exercises)
        # Map exercise id to linear position 1..N across the course
        exercise_pos = {ex.id: idx + 1 for idx, ex in enumerate(ordered_exercises)}

        # Active members
        memberships = (
            CohortMembership.objects
            .filter(cohort=selected_cohort, status='active')
            .select_related('student')
        )

        # Preload attempts and interactions for the cohort to compute metrics
        student_ids = [m.student_id for m in memberships]
        attempts = (
            Attempt.objects
            .filter(user_id__in=student_ids, cohort=selected_cohort)
            .select_related('exercise__module')
        )
        # Map: student_id -> list of attempts
        attempts_by_student = {}
        for a in attempts:
            attempts_by_student.setdefault(a.user_id, []).append(a)

        # Fetch interactions for all attempts in one query
        attempt_ids = [a.id for a in attempts]
        interactions = AttemptInteraction.objects.filter(attempt_id__in=attempt_ids).order_by('attempt_id', 'submitted_at')
        # Map: attempt_id -> list of interactions (in order)
        interactions_by_attempt = {}
        for inter in interactions:
            interactions_by_attempt.setdefault(inter.attempt_id, []).append(inter)

        # Compute per-student metrics
        percents = []
        # Prepare histogram buckets for 0..total_exercises (0 = none completed)
        bucket_map = {k: [] for k in range(0, max(total_exercises, 0) + 1)}
        # Prepare per-exercise completion counts (aligned with positions; index 0 left unused for alignment)
        exercise_counts = [0 for _ in range(0, max(total_exercises, 0) + 1)]

        # Sort memberships by last_name, first_name (fallback username)
        def name_key(m):
            u = m.student
            last = (u.last_name or '').lower()
            first = (u.first_name or '').lower()
            username = (u.username or '').lower()
            return (last, first, username)

        memberships_sorted = sorted(memberships, key=name_key)

        for m in memberships_sorted:
            user = m.student
            user_attempts = attempts_by_student.get(user.id, [])

            # Completed (distinct visible exercises completed in this cohort)
            completed_exercise_ids = set(
                a.exercise_id for a in user_attempts if a.complete and getattr(a.exercise, 'visible', True)
            )
            completed_count = len(completed_exercise_ids)

            percent = int(round((completed_count / total_exercises) * 100)) if total_exercises > 0 else 0
            percents.append(percent)

            # Last attempt in this cohort (by updated_at)
            last_attempt = max(user_attempts, key=lambda a: a.updated_at, default=None)
            last_exercise = last_attempt.exercise if last_attempt else None

            # Submissions and hints count
            submissions_count = 0
            hints_count = 0

            for a in user_attempts:
                inters = interactions_by_attempt.get(a.id, [])
                for log in inters:
                    meta = (log.interaction or {}).get('user_submission', {}).get('metadata', {})
                    action = meta.get('action')
                    # Count submissions and hints
                    if action in ('run_code', 'run_query', 'submit_answer'):
                        submissions_count += 1
                    if action == 'ask_hint':
                        hints_count += 1

            # Average time per exercise: over distinct attempted exercises within cohort
            # (time metrics deferred)

            students_data.append({
                'user': user,
                'completed_count': completed_count,
                'total_exercises': total_exercises,
                'percent': percent,
                'last_exercise': last_exercise,
                'last_attempt_complete': bool(getattr(last_attempt, 'complete', False)) if last_attempt else False,
                'submissions_count': submissions_count,
                'hints_count': hints_count,
            })

            # Add to histogram bucket: highest completed exercise index across the course
            try:
                display_name = (user.last_name or '').strip()
                if user.first_name:
                    display_name = f"{display_name}, {user.first_name.strip()}" if display_name else user.first_name.strip()
                if not display_name:
                    display_name = (user.username or '').strip()
            except Exception:
                display_name = (getattr(user, 'username', '') or '').strip()
            if completed_exercise_ids:
                highest_pos = max((exercise_pos.get(eid, 0) for eid in completed_exercise_ids), default=0)
            else:
                highest_pos = 0
            bucket_map.setdefault(highest_pos, []).append(display_name)

            # Increment per-exercise counts for all completed exercises
            for eid in completed_exercise_ids:
                pos = exercise_pos.get(eid)
                if pos is not None:
                    exercise_counts[pos] += 1

        # Build histogram data for template
        hist = []
        for k in range(0, max(total_exercises, 0) + 1):
            names = sorted(bucket_map.get(k, []), key=lambda s: s.lower())
            hist.append({'position': k, 'count': len(names), 'names': names})
        # Compute max for scaling
        max_bar_count = max((h['count'] for h in hist), default=0)
        # Precompute bar heights in pixels to avoid template arithmetic
        MAX_BAR_HEIGHT_PX = 120
        for h in hist:
            if max_bar_count > 0:
                h['height_px'] = int(round((h['count'] * MAX_BAR_HEIGHT_PX) / max_bar_count))
            else:
                h['height_px'] = 0
        histogram = hist

        # Build per-exercise percentage bars aligned with positions
        active_members_count = memberships_sorted.__len__()
        exercise_completion_bars = []
        MAX_BAR_HEIGHT_PX2 = 120
        for pos in range(0, max(total_exercises, 0) + 1):
            count = exercise_counts[pos]
            percent = int(round((count / active_members_count) * 100)) if active_members_count > 0 else 0
            height_px = int(round((percent / 100) * MAX_BAR_HEIGHT_PX2))
            exercise_completion_bars.append({
                'position': pos,
                'count': count,
                'total': active_members_count,
                'percent': percent,
                'height_px': height_px,
            })

    # All cohorts for selector
    all_cohorts = Cohort.objects.filter(owner=request.user).select_related('course').order_by('course__name', 'name')

    return render(request, 'exercises/teacher/dashboard.html', {
        'selected_cohort': selected_cohort,
        'cohorts': all_cohorts,
        'students': students_data,
        'histogram': histogram,
        'max_bar_count': max_bar_count,
        'exercise_completion_bars': exercise_completion_bars if selected_cohort else [],
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
    # Remember last visited course for teacher dashboard defaulting
    try:
        request.session['last_teacher_course_id'] = course.id
    except Exception:
        pass

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


