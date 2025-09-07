from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.db import transaction, models
import json

from .decorators import teacher_required
from .models import Exercise, Course, Module, ExerciceAsset, Cohort, CohortMembership, Attempt, Trace, create_trace_for
from django.contrib.contenttypes.models import ContentType
from .unit_testing import run_unit_tests
from .logic import generate_authoring_update
from .logic import generate_i18n_translations
from .schemas import ExerciseData, AnswerData
from pydantic import ValidationError


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
        # Helper: map linear position -> label ("1.2") and 0 -> em dash
        def position_label(position: int) -> str:
            if position <= 0:
                return '—'
            try:
                ex = ordered_exercises[position - 1]
                return ex.sequence_label or str(position)
            except Exception:
                return str(position)
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

        # Fetch traces for all attempts in one query
        attempt_ids = [a.id for a in attempts]
        attempt_ct = ContentType.objects.get_for_model(Attempt, for_concrete_model=False)
        traces = (
            Trace.objects
            .filter(content_type=attempt_ct, object_id__in=attempt_ids)
            .order_by('object_id', 'rank_order', 'id')
        )
        # Map: attempt_id -> list of traces (in order)
        interactions_by_attempt = {}
        for tr in traces:
            interactions_by_attempt.setdefault(tr.object_id, []).append(tr)

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
                for tr in inters:
                    meta = (tr.user_metadata or {})
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
            hist.append({'position': k, 'label': position_label(k), 'count': len(names), 'names': names})
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
                'label': position_label(pos),
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
        # Strict new contract only
        try:
            source_module_id = int(data['source_module_id'])
            target_module_id = int(data['target_module_id'])
            source_exercise_ids = [int(eid) for eid in (data.get('source_exercise_ids') or [])]
            target_exercise_ids = [int(eid) for eid in (data.get('target_exercise_ids') or [])]
            moved_exercise_id = int(data['moved_exercise_id'])
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Invalid payload: require integer ids for modules and exercises'}, status=400)

        # Validate memberships and apply updates
        if source_module_id == target_module_id:
            # Intra-module: All ids must belong to that module
            count = Exercise.objects.filter(id__in=target_exercise_ids, module_id=source_module_id).count()
            if count != len(target_exercise_ids):
                return JsonResponse({'status': 'error', 'message': 'Exercise IDs must belong to the same module'}, status=400)

            # Bulk CASE reorder with offset trick
            all_ids_in_module = list(
                Exercise.objects.filter(module_id=source_module_id).order_by('order').values_list('id', flat=True)
            )
            ordered_ids = target_exercise_ids + [eid for eid in all_ids_in_module if eid not in target_exercise_ids]

            big_offset = 1000000
            temp_when = [models.When(id=eid, then=big_offset + idx) for idx, eid in enumerate(ordered_ids)]
            Exercise.objects.filter(id__in=ordered_ids).update(order=models.Case(*temp_when))
            final_when = [models.When(id=eid, then=idx) for idx, eid in enumerate(ordered_ids)]
            Exercise.objects.filter(id__in=ordered_ids).update(order=models.Case(*final_when))
        else:
            # Cross-module: ensure payload shape and prevent unique constraint collisions
            if moved_exercise_id not in target_exercise_ids:
                return JsonResponse({'status': 'error', 'message': 'moved_exercise_id must be present in target_exercise_ids'}, status=400)

            # Lock the two modules to avoid concurrent reorder conflicts
            Module.objects.select_for_update().filter(id__in=[source_module_id, target_module_id]).order_by('id').values_list('id', flat=True)

            # Validate source and target memberships (allow moved exercise to be absent from target until we move it)
            src_count = Exercise.objects.filter(id__in=source_exercise_ids, module_id=source_module_id).count()
            if src_count != len(source_exercise_ids):
                return JsonResponse({'status': 'error', 'message': 'Source exercise IDs do not match source module'}, status=400)

            target_ids_wo_moved = [eid for eid in target_exercise_ids if eid != moved_exercise_id]
            tgt_count = Exercise.objects.filter(id__in=target_ids_wo_moved, module_id=target_module_id).count()
            if tgt_count != len(target_ids_wo_moved):
                return JsonResponse({'status': 'error', 'message': 'Target exercise IDs (excluding moved) do not match target module'}, status=400)

            big_offset = 1000000

            # 1) Temporarily shift orders away in both modules to avoid collisions
            if source_exercise_ids:
                src_temp = [models.When(id=eid, then=big_offset + 10 + idx) for idx, eid in enumerate(source_exercise_ids)]
                Exercise.objects.filter(id__in=source_exercise_ids).update(order=models.Case(*src_temp))

            if target_ids_wo_moved:
                tgt_temp = [models.When(id=eid, then=big_offset + 20 + idx) for idx, eid in enumerate(target_ids_wo_moved)]
                Exercise.objects.filter(id__in=target_ids_wo_moved).update(order=models.Case(*tgt_temp))

            # 2) Move the exercise to target module with a unique temporary order distinct from others
            Exercise.objects.filter(pk=moved_exercise_id).update(module_id=target_module_id, order=big_offset + 1)

            # 3) Apply final orders
            if source_exercise_ids:
                src_final = [models.When(id=eid, then=idx) for idx, eid in enumerate(source_exercise_ids)]
                Exercise.objects.filter(id__in=source_exercise_ids).update(order=models.Case(*src_final))

            tgt_final = [models.When(id=eid, then=idx) for idx, eid in enumerate(target_exercise_ids)]
            Exercise.objects.filter(id__in=target_exercise_ids).update(order=models.Case(*tgt_final))

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
@require_POST
@transaction.atomic
def duplicate_exercise(request, exercise_id):
    try:
        original = get_object_or_404(Exercise.objects.select_related('module'), pk=exercise_id)
        module = original.module

        # Lock the module's exercises to avoid concurrent reorder conflicts
        Module.objects.select_for_update().filter(pk=module.pk).values_list('id', flat=True)

        # Snapshot existing exercises order within the module
        existing = list(
            Exercise.objects
            .filter(module=module)
            .order_by('order', 'id')
            .values('id')
        )
        existing_ids = [row['id'] for row in existing]
        if original.id not in existing_ids:
            return JsonResponse({'status': 'error', 'message': 'Original exercise not found in its module ordering'}, status=400)

        original_index = existing_ids.index(original.id)

        # 1) Temporarily shift all orders away to avoid unique (module, order) collisions
        big_offset = 1000000
        # Leave a small gap so we can place the duplicate at a distinct temporary order
        temp_when = [models.When(id=eid, then=big_offset + 10 + idx) for idx, eid in enumerate(existing_ids)]
        if temp_when:
            Exercise.objects.filter(id__in=existing_ids).update(order=models.Case(*temp_when))

        # 2) Create the duplicated exercise with a temporary distinct order
        title_copy = dict(original.title_i18n or {})
        try:
            # Append " (copy)" to English title for clarity
            base_en = title_copy.get('en') or original.title or ''
            title_copy['en'] = (base_en + ' (copy)').strip()
        except Exception:
            # Fallback: ensure at least an English marker
            title_copy['en'] = (original.title or 'Exercise') + ' (copy)'

        duplicate = Exercise(
            module=module,
            title_i18n=title_copy,
            description_i18n=dict(original.description_i18n or {}),
            question_i18n=dict(original.question_i18n or {}),
            exercise_type=original.exercise_type,
            # Use a unique temporary order that won't collide with shifted ones
            order=big_offset + 1,
            exercise_data=dict(original.exercise_data or {}),
            answer_data=dict(original.answer_data or {}),
            visible=original.visible,
        )
        duplicate.save()

        # 3) Apply final contiguous orders inserting the duplicate right after the original
        final_ids = existing_ids[: original_index + 1] + [duplicate.id] + existing_ids[original_index + 1 :]
        final_when = [models.When(id=eid, then=idx) for idx, eid in enumerate(final_ids)]
        Exercise.objects.filter(id__in=final_ids).update(order=models.Case(*final_when))

        # If called via form POST with redirect flag, go straight to edit page
        if (request.POST.get('redirect') == '1'):
            return redirect('teachers:exercise_edit', course_pk=module.course_id, exercise_pk=duplicate.id)

        return JsonResponse({'status': 'success', 'new_exercise_id': duplicate.id})
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
            question_i18n={"en": ""},
            exercise_data={},
            answer_data={"unit_tests": {"setup_code": "", "test_cases": [], "timeout_seconds": 5}, "hints": ""},
        )

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            # Title/description/question i18n
            title_i18n = data.get('title_i18n') or {}
            description_i18n = data.get('description_i18n') or {}
            question_i18n = data.get('question_i18n') or {}

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

            exercise.exercise_type = data.get('exercise_type', 'python')
            ex_data = data.get('exercise_data', {}) or {}
            
            try:
                exercise.exercise_data = ExerciseData.model_validate(ex_data).model_dump(exclude_unset=True)
                answer_data = data.get('answer_data', {}) or {}
                exercise.answer_data = AnswerData.model_validate(answer_data).model_dump(exclude_unset=True)
            except ValidationError as e:
                return JsonResponse({'status': 'error', 'message': f"Invalid data format: {e}"}, status=400)

            exercise.title_i18n = title_i18n
            exercise.description_i18n = description_i18n
            exercise.question_i18n = question_i18n
            
            if exercise.exercise_type == 'python' and 'unit_tests' in exercise.answer_data:
                unit_tests = exercise.answer_data_obj.unit_tests.model_dump()
                correct_answers = exercise.answer_data_obj.correct_answers
                for i, correct_answer in enumerate(correct_answers):
                    code_to_test = correct_answer.answer
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
        "title_i18n": exercise.title_i18n,
        "order": exercise.order,
        "description_i18n": exercise.description_i18n,
        "question_i18n": exercise.question_i18n,
        "exercise_type": exercise.exercise_type,
        "exercise_data": exercise.exercise_data_obj.model_dump(),
        "answer_data": exercise.answer_data_obj.model_dump(),
        "available_sql_assets": available_sql_assets,
        "course_pk": course.pk,
        "course_name": course.name,
        "course_description": course.description,
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

    exercise_payload = body.get('exercise') or {}  # the exercise object that the LLM is helping to improve
    messages = body.get('messages') or []  # the user/assistant conversation
    context = body.get('context') or {}  # the course object
    course_pk = context.get('course_pk')

    if not isinstance(messages, list):
        return JsonResponse({'status': 'error', 'message': 'messages must be a list'}, status=400)

    if not course_pk:
        return JsonResponse({'status': 'error', 'message': 'Missing course_pk in context'}, status=400)

    course = get_object_or_404(Course, pk=course_pk)

    print(f"exercise_payload: {exercise_payload}")
    print(f"messages: {messages}")
    print(f"course: {course}")

    try:
        result = generate_authoring_update(exercise_payload=exercise_payload, messages=messages, course=course)

        # Persist authoring interaction as a Trace
        exercise_pk = (exercise_payload or {}).get('pk') or (exercise_payload or {}).get('id')

        trace_object = None
        if exercise_pk:
            try:
                trace_object = Exercise.objects.get(pk=int(exercise_pk), module__course=course)
            except (Exercise.DoesNotExist, ValueError, TypeError):
                # Fallback to course if exercise not found or pk is invalid
                trace_object = course
        else:
            trace_object = course
        
        try:
            user_text = ''
            try:
                if isinstance(messages, list) and messages:
                    last_msg = messages[-1] or {}
                    if (last_msg.get('role') or 'user') == 'user':
                        user_text = str(last_msg.get('content') or '')
            except Exception:
                user_text = ''

            assistant_text = str(result.get('assistant_message') or '')
            updated_exercise_payload = result.get('updated_exercise') or {}
            fields = {
                'user_content': user_text,
                'assistant_content': assistant_text,
                'assistant_metadata': {
                    'updated_exercise': updated_exercise_payload,
                    'model': result.get('assistant_metadata', {}).get('model'),
                    'usage': result.get('assistant_metadata', {}).get('usage'),
                    'finish_reason': result.get('assistant_metadata', {}).get('finish_reason'),
                },
            }
            
            trace_ct = ContentType.objects.get_for_model(trace_object, for_concrete_model=False)
            has_any = Trace.objects.filter(content_type=trace_ct, object_id=trace_object.pk, channel='authoring').exists()
            if not has_any:
                fields['system_prompt'] = str(result.get('system_prompt') or '')
            
            create_trace_for(trace_object, request.user, channel='authoring', **fields)
        except Exception as e:
            # Best-effort persistence; do not fail the request on logging errors
            print(f"Error persisting authoring interaction as a Trace: {e}")
            pass

        return JsonResponse({'status': 'success', **result})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

        
@login_required
@teacher_required
@require_POST
def translate_i18n(request):
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    source_lang = (body.get('source_lang') or 'en').strip()
    targets = body.get('targets') or []
    fields = body.get('fields') or {}
    course_context = body.get('course_context') or {}

    if not isinstance(targets, list) or not targets:
        return JsonResponse({'status': 'error', 'message': 'targets must be a non-empty list'}, status=400)

    try:
        result = generate_i18n_translations(
            source_lang=source_lang,
            targets=targets,
            fields=fields,
            course_context=course_context,
        )
        return JsonResponse({'status': 'success', 'translations': result})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)



