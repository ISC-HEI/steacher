from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST, require_http_methods
from django.db import transaction, models
import json
import logging
from .authz import (
    course_roles_required,
    assert_can_edit_course,
    assert_can_view_course,
    cohort_roles_required,
)
from .models import Exercise, Course, Module, ExerciseAsset, Cohort, CohortMembership, Attempt, create_trace_for, CourseMembership, Trace
from .unit_testing import run_unit_tests, run_unit_tests_scala
from .logic import generate_authoring_update
from .logic import generate_i18n_translations
from .schemas import ExerciseData, AnswerData
from pydantic import ValidationError
from django.contrib.auth import get_user_model
from itertools import groupby
from operator import attrgetter
import newrelic.agent as nr
from django.contrib import messages
from django.utils import timezone
from django.db.models import Avg, Count, F, ExpressionWrapper, fields, Subquery, OuterRef, Q, Max, Min
from django.db.models.functions import Cast, JSONObject
from django.utils import timezone
from datetime import timedelta
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.fields import GenericRelation


def get_exercise_analytics(exercises, filter_days_str='all'):
    """
    Calculates analytics metrics for a queryset of exercises.
    """
    exercise_metrics = []
    
    # Handle date filtering setup
    start_date = None
    if filter_days_str.isdigit():
        start_date = timezone.now() - timedelta(days=int(filter_days_str))

    # Base attempts queryset for all exercises in the list
    base_attempts = Attempt.objects.filter(exercise__in=exercises)
    if start_date:
        base_attempts = base_attempts.filter(updated_at__gte=start_date)

    for exercise in exercises:
        attempts_for_exercise = base_attempts.filter(exercise=exercise)
        
        if filter_days_str == 'last_edit':
            attempts_for_exercise = attempts_for_exercise.filter(updated_at__gte=exercise.updated_at)

        # Calculate metrics for the filtered attempts
        metrics = attempts_for_exercise.aggregate(
            total_attempts=Count('id', distinct=True),
            completed_attempts=Count('id', filter=Q(complete=True), distinct=True),
            avg_time_to_complete=Avg(
                ExpressionWrapper(F('updated_at') - F('created_at'), output_field=fields.DurationField()),
                filter=Q(complete=True)
            )
        )
        
        # Calculate perplexity from traces
        traces_for_exercise = Trace.objects.filter(
            object_id__in=Subquery(attempts_for_exercise.values('id')),
            content_type=ContentType.objects.get_for_model(Attempt),
            channel='exercise_guidance',
            assistant_metadata__uncertainty__perplexity__isnull=False
        )
        
        perplexity_avg = traces_for_exercise.aggregate(
            avg_perplexity=Avg(Cast(F('assistant_metadata__uncertainty__perplexity'), fields.FloatField()))
        )['avg_perplexity']

        # Calculate iterations and hints
        iterations_and_hints = attempts_for_exercise.aggregate(
            total_iterations=Count('traces', filter=Q(traces__channel='exercise_guidance')),
            total_hints=Count('traces', filter=Q(traces__user_metadata__action='ask_hint'))
        )
        
        # Combine and format metrics
        total_attempts = metrics['total_attempts']
        completed_attempts = metrics['completed_attempts']
        
        avg_iterations = (iterations_and_hints['total_iterations'] / total_attempts) if total_attempts > 0 else 0
        avg_hints = (iterations_and_hints['total_hints'] / total_attempts) if total_attempts > 0 else 0
        completion_rate = (completed_attempts / total_attempts * 100) if total_attempts > 0 else 0
        avg_time_seconds = metrics['avg_time_to_complete'].total_seconds() if metrics['avg_time_to_complete'] else 0

        exercise_metrics.append({
            'exercise': exercise,
            'avg_perplexity': perplexity_avg,
            'avg_iterations': avg_iterations,
            'completion_rate': completion_rate,
            'avg_time_seconds': avg_time_seconds,
            'avg_hints': avg_hints,
        })

    # Sort by perplexity by default
    exercise_metrics.sort(key=lambda x: (x['avg_perplexity'] is None, x['avg_perplexity']), reverse=True)
    return exercise_metrics


User = get_user_model()

logger = logging.getLogger(__name__)


@login_required
@course_roles_required(['owner','editor', 'viewer'], course_kw='pk')
def course_detail(request, pk):
    course: Course = request.course
    # Remember last visited course for teacher dashboard defaulting
    try:
        request.session['last_teacher_course_id'] = course.id
    except Exception: # pylint: disable=broad-exception-caught
        pass
    # Compute which exercises are completed by the current user for per-exercise checkmarks
    completed_ids = set()
    return render(request, 'exercises/teacher/teachers_course_details.html', {
        'course': course,
        'completed_exercise_ids': completed_ids,
    })


@login_required
@course_roles_required(['owner','editor'], course_kw='pk')
@require_http_methods(["GET", "POST"])
def course_edit(request, pk):
    """
    Edit a course's name, system prompt and LLM prompts (per exercise type).
    Only accessible to course owners and editors.
    """
    course: Course = request.course

    exercise_type_choices: list[str] = [t[0] for t in Exercise.EXERCISE_TYPE_CHOICES]

    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        system_prompt = (request.POST.get('system_prompt') or '').strip()

        # Collect per-type prompts from form fields "llm_prompts__<type_key>"
        llm_prompts_val = {}
        for key in exercise_type_choices:
            value = (request.POST.get(f"llm_prompts__{key}") or '').strip()
            if value:
                llm_prompts_val[key] = value
            else:
                llm_prompts_val[key] = ''

        # Basic validation
        if not name:
            messages.error(request, 'Course name is required.')
        else:
            course.name = name
            course.system_prompt = system_prompt
            course.llm_prompts = llm_prompts_val
            course.save(update_fields=['name', 'system_prompt', 'llm_prompts', 'updated_at'])
            messages.success(request, 'Course settings updated.')
            return redirect('teachers:course_detail', pk=course.pk)

    # GET -> render form with current values
    llm_type_fields = [
        {
            'key': key,
            'value': (course.llm_prompts or {}).get(key, ''),
        }
        for key in exercise_type_choices
    ]
    context = {
        'course': course,
        'initial': {
            'name': course.name or '',
            'system_prompt': course.system_prompt or '',
        },
        'llm_type_fields': llm_type_fields,
    }
    return render(request, 'exercises/teacher/course_edit.html', context)


@login_required
def course_analytics_dashboard(request, course_id):
    """
    Displays the course analytics dashboard for exercises and performance metrics.
    """
    course = get_object_or_404(Course, pk=course_id)
    assert_can_view_course(request.user, course)

    # Handle date filtering
    filter_days_str = request.GET.get('filter', 'all')
    
    # Get all exercises for the course and calculate metrics
    exercises = Exercise.objects.filter(module__course=course).select_related('module').order_by('module__order', 'order')
    exercise_metrics = get_exercise_analytics(exercises, filter_days_str)

    context = {
        'course': course,
        'course_name': course.name,
        'nav': 'courses',
        'exercise_metrics': exercise_metrics,
        'day_filters': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        'selected_filter': filter_days_str,
    }
    
    return render(request, 'exercises/teacher/course_analytics_dashboard.html', context)


@login_required
def exercise_analytics_detail(request, exercise_id):
    """
    Displays analytics for a single exercise (e.g., top uncertain interactions).
    """
    exercise = get_object_or_404(Exercise, pk=exercise_id)
    assert_can_view_course(request.user, exercise.module.course)

    # Handle date filtering
    filter_days_str = request.GET.get('filter', 'all')
    end_date = timezone.now()
    start_date = None

    if filter_days_str.isdigit():
        start_date = end_date - timedelta(days=int(filter_days_str))

    # Base attempts queryset
    attempts = Attempt.objects.filter(exercise=exercise)
    if start_date:
        attempts = attempts.filter(updated_at__gte=start_date)
    elif filter_days_str == 'last_edit':
        attempts = attempts.filter(updated_at__gte=exercise.updated_at)

    # Get top 20 uncertain traces
    uncertain_traces = Trace.objects.filter(
        object_id__in=Subquery(attempts.values('id')),
        content_type=ContentType.objects.get_for_model(Attempt),
        channel='exercise_guidance',
        assistant_metadata__uncertainty__perplexity__isnull=False
    ).order_by(
        Cast(F('assistant_metadata__uncertainty__perplexity'), fields.FloatField()).desc()
    )[:20]

    # Prepare scaled progress values for the template
    scale_factor = 30.0
    trace_items = []
    for tr in uncertain_traces:
        metadata = tr.assistant_metadata or {}
        uncertainty = metadata.get('uncertainty') or {}
        try:
            perplexity_val = float(uncertainty.get('perplexity') or 0.0)
        except Exception:
            perplexity_val = 0.0
        percent = perplexity_val * scale_factor
        if percent < 0:
            percent = 0.0
        if percent > 100:
            percent = 100.0
        trace_items.append({
            'trace': tr,
            'perplexity': perplexity_val,
            'percent': percent,
        })

    context = {
        'exercise': exercise,
        'nav': 'courses',
        'trace_items': trace_items,
        'scale_factor': int(scale_factor),
    }
    return render(request, 'exercises/teacher/exercise_analytics_detail.html', context)


@login_required
def dashboard(request):
    """Teacher dashboard: landing listing courses and cohorts."""
    # Courses via direct course roles (owner/editor)
    courses_via_roles = Course.objects.filter(
        id__in=CourseMembership.objects.filter(
            user=request.user, role__in=['owner', 'editor']
        ).values_list('course', flat=True)
    )
    # Courses via cohorts where user is teacher/owner
    courses_via_cohorts = Course.objects.filter(
        id__in=CohortMembership.objects.filter(
            user=request.user, role__in=['teacher', 'owner'], status='active'
        ).values_list('cohort__course', flat=True)
    )
    courses = courses_via_roles.union(courses_via_cohorts).order_by('name')

    # For link decisions in the template: which courses can the user edit?
    editable_course_ids = list(
        CourseMembership.objects
        .filter(user=request.user, role__in=['owner', 'editor'])
        .values_list('course_id', flat=True)
    )

    # Cohorts where user is teacher/owner
    cohorts = (
        Cohort.objects
        .filter(memberships__user=request.user, memberships__role__in=['teacher', 'owner'])
        .select_related('course')
        .order_by('course__name', 'name')
        .distinct()
    )

    return render(request, 'exercises/teacher/dashboard.html', {
        'courses': courses,
        'cohorts': cohorts,
        'editable_course_ids': editable_course_ids,
    })


@login_required
@cohort_roles_required(['owner', 'teacher', 'viewer'], cohort_kw='pk')
def cohort_detail(request, pk): # pylint: disable=unused-argument
    """Cohort detail analytics page (moved from old dashboard)."""
    selected_cohort = request.cohort
    try:
        request.session['last_teacher_cohort_id'] = selected_cohort.id
    except Exception:
        pass

    # Build dataset for Grid.js (simple JSON rows only)
    students_json = []
    histogram = []
    max_bar_count = 0
    exercise_completion_bars = []

    course: Course = selected_cohort.course
    ordered_exercises = list(
        Exercise.objects
        .filter(module__course=course, visible=True)
        .select_related('module')
        .order_by('module__order', 'order')
    )
    total_exercises = len(ordered_exercises)

    def position_label(position: int) -> str:
        if position <= 0:
            return '—'
        try:
            ex = ordered_exercises[position - 1]
            return ex.sequence_label or str(position)
        except Exception:
            return str(position)

    exercise_pos = {ex.id: idx + 1 for idx, ex in enumerate(ordered_exercises)}

    memberships = (
        CohortMembership.objects
        .filter(cohort=selected_cohort, status='active', role='student')
        .select_related('user')
    )

    student_ids = [m.user_id for m in memberships]
    attempts = (
        Attempt.objects
        .filter(user_id__in=student_ids, cohort=selected_cohort)
        .select_related('exercise__module')
    )

    attempts_by_student = {}
    for a in attempts:
        attempts_by_student.setdefault(a.user_id, []).append(a)

    interactions_by_attempt = {a.id: list(a.traces.all().order_by('rank_order', 'id')) for a in attempts}

    bucket_map = {k: [] for k in range(0, max(total_exercises, 0) + 1)}
    exercise_counts = [0 for _ in range(0, max(total_exercises, 0) + 1)]

    def name_key(m):
        u = m.user
        return u.get_display_name().lower()

    memberships_sorted = sorted(memberships, key=name_key)

    for idx, m in enumerate(memberships_sorted, start=1):
        user = m.user
        user_attempts = attempts_by_student.get(user.id, [])

        completed_exercise_ids = set(
            a.exercise_id for a in user_attempts if a.complete and getattr(a.exercise, 'visible', True)
        )
        completed_count = len(completed_exercise_ids)
        percent = int(round((completed_count / total_exercises) * 100)) if total_exercises > 0 else 0

        last_attempt = max(user_attempts, key=lambda a: a.updated_at, default=None)
        last_exercise = last_attempt.exercise if last_attempt else None

        hints_count = 0
        submissions_count = 0
        questions_count = 0
        interactions_count = 0
        # Counters restricted to completed exercises only
        hints_on_completed = 0
        submissions_on_completed = 0
        questions_on_completed = 0
        interactions_on_completed = 0
        reveals_on_completed = 0
        for a in user_attempts:
            inters = interactions_by_attempt.get(a.id, [])
            interactions_count += len(inters)
            is_completed_attempt = bool(getattr(a, 'complete', False)) and getattr(getattr(a, 'exercise', None), 'visible', True)
            for tr in inters:
                meta = (tr.user_metadata or {})
                action = meta.get('action')
                if action == 'ask_hint':
                    hints_count += 1
                elif action == 'ask_question':
                    questions_count += 1
                elif action in ('run_submission', 'submit_answer'):
                    submissions_count += 1
            if is_completed_attempt:
                interactions_on_completed += len(inters)
                # Count solution reveal flag per completed attempt
                try:
                    if getattr(a, 'asked_for_solution', False):
                        reveals_on_completed += 1
                except Exception:
                    pass
                for tr in inters:
                    meta2 = (tr.user_metadata or {})
                    act2 = meta2.get('action')
                    if act2 == 'ask_hint':
                        hints_on_completed += 1
                    elif act2 == 'ask_question':
                        questions_on_completed += 1
                    elif act2 in ('run_submission', 'submit_answer'):
                        submissions_on_completed += 1

        # Append a lightweight row for frontend Grid.js
        students_json.append({
            'id': getattr(user, 'id', None),
            'display_name': user.get_display_name(),
            'student_number': idx,
            'percent': percent,
            'completed_count': completed_count,
            'total_exercises': total_exercises,
            'last_exercise_id': getattr(last_exercise, 'id', None) if last_exercise else None,
            'last_exercise_title': getattr(last_exercise, 'title', '') if last_exercise else '',
            'last_attempt_complete': bool(getattr(last_attempt, 'complete', False)) if last_attempt else False,
            'avg_hints_per_completed': (hints_on_completed / completed_count) if completed_count > 0 else 0.0,
            'avg_submissions_per_completed': (submissions_on_completed / completed_count) if completed_count > 0 else 0.0,
            'avg_questions_per_completed': (questions_on_completed / completed_count) if completed_count > 0 else 0.0,
            'avg_interactions_per_completed': (interactions_on_completed / completed_count) if completed_count > 0 else 0.0,
            'avg_solution_reveals_per_completed': (reveals_on_completed / completed_count) if completed_count > 0 else 0.0,
        })

        if completed_exercise_ids:
            highest_pos = max((exercise_pos.get(eid, 0) for eid in completed_exercise_ids), default=0)
        else:
            highest_pos = 0
        bucket_map.setdefault(highest_pos, []).append(user.get_display_name())

        for eid in completed_exercise_ids:
            pos = exercise_pos.get(eid)
            if pos is not None:
                exercise_counts[pos] += 1

    hist = []
    for k in range(0, max(total_exercises, 0) + 1):
        names = sorted(bucket_map.get(k, []), key=lambda s: s.lower())
        hist.append({'position': k, 'label': position_label(k), 'count': len(names), 'names': names})
    max_bar_count = max((h['count'] for h in hist), default=0)
    MAX_BAR_HEIGHT_PX = 120
    for h in hist:
        if max_bar_count > 0:
            h['height_px'] = int(round((h['count'] * MAX_BAR_HEIGHT_PX) / max_bar_count))
        else:
            h['height_px'] = 0
    histogram = hist

    active_members_count = memberships_sorted.__len__()
    MAX_BAR_HEIGHT_PX2 = 120
    for pos in range(0, max(total_exercises, 0) + 1):
        count = exercise_counts[pos]
        percent = int(round((count / active_members_count) * 100)) if active_members_count > 0 else 0
        height_px = int(round((percent / 100) * MAX_BAR_HEIGHT_PX2))
        exercise_id = ordered_exercises[pos-1].id if pos > 0 else 0
        exercise_completion_bars.append({
            'position': pos,
            'label': position_label(pos),
            'count': count,
            'total': active_members_count,
            'percent': percent,
            'height_px': height_px,
            'exercise_id': exercise_id,
        })

    return render(request, 'exercises/teacher/cohort.html', {
        'selected_cohort': selected_cohort,
        'students_json': students_json,
        'histogram': histogram,
        'max_bar_count': max_bar_count,
        'exercise_completion_bars': exercise_completion_bars,
    })


@login_required
@cohort_roles_required(['owner', 'teacher', 'viewer'], cohort_kw='cohort_id')
def cohort_student_detail(request, cohort_id, student_id):  # pylint: disable=unused-argument
    """Cohort student detail page. Packs the exercises and attempts for the student into a single page, sorted by module."""
    selected_cohort: Cohort = request.cohort
    student: User = get_object_or_404(get_user_model(), pk=student_id)
    course: Course = selected_cohort.course
    
    exercises = Exercise.objects.filter(
        module__course=course
    ).select_related('module').order_by('module__order', 'order')
    
    attempts = Attempt.objects.filter(
        user=student,
        cohort=selected_cohort,
        exercise__in=exercises
    ).prefetch_related('traces')

    attempts_by_exercise = {attempt.exercise_id: attempt for attempt in attempts}

    total_hints = 0
    modules_data = []
    for module, module_exercises_iter in groupby(exercises, key=attrgetter('module')):
        module_exercises = []
        for exercise in module_exercises_iter:
            attempt = attempts_by_exercise.get(exercise.id)
            traces = sorted(attempt.traces.all(), key=lambda t: t.rank_order) if attempt else []
            
            hints_count = 0
            for trace in traces:
                if trace.user_metadata.get('action') == 'ask_hint':
                    hints_count += 1
            total_hints += hints_count

            module_exercises.append({
                'exercise': exercise,
                'attempt': attempt,
                'traces': traces,
                'submissions_count': len(traces),
                'hints_count': hints_count,
            })
        modules_data.append({
            'module': module,
            'exercises': module_exercises
        })

    completed_count = sum(1 for m in modules_data for e in m['exercises'] if e['attempt'] and e['attempt'].complete)
    attempted_count = sum(1 for m in modules_data for e in m['exercises'] if e['attempt'])
    total_exercises = len(exercises)

    return render(request, 'exercises/teacher/cohort_student_detail.html', {
        'selected_cohort': selected_cohort,
        'student': student,
        'modules_data': modules_data,
        'total_exercises': total_exercises,
        'completed_count': completed_count,
        'attempted_count': attempted_count,
        'total_hints': total_hints,
    })


@login_required
@cohort_roles_required(['owner', 'teacher', 'viewer'], cohort_kw='cohort_id')
def cohort_exercise_detail(request, cohort_id, exercise_id): # pylint: disable=unused-argument
    """Exercise detail page for a cohort."""
    selected_cohort: Cohort = request.cohort
    exercise: Exercise = get_object_or_404(Exercise, pk=exercise_id)

    students = User.objects.filter(cohort_memberships__cohort=selected_cohort, cohort_memberships__role='student').distinct()
    attempts = Attempt.objects.filter(
        cohort=selected_cohort,
        exercise=exercise,
        user__in=students
    ).prefetch_related('traces')
    attempts_by_user = {attempt.user_id: attempt for attempt in attempts}

    student_data = []
    total_submissions = 0
    total_hints = 0
    completed_submissions = []

    for student in students:
        attempt = attempts_by_user.get(student.id)
        traces = attempt.traces.all() if attempt else []
        
        hints_count = 0
        for trace in traces:
            if trace.user_metadata.get('action') == 'ask_hint':
                hints_count += 1
        
        total_submissions += len(traces)
        total_hints += hints_count
        if attempt and attempt.complete:
            completed_submissions.append(len(traces))

        student_data.append({
            'student': student,
            'attempt': attempt,
            'submissions_count': len(traces),
            'hints_count': hints_count,
        })

    # Stats
    total_students = len(students)
    completed_count = len(completed_submissions)
    attempted_count = len(attempts) - completed_count
    not_started_count = total_students - len(attempts)
    avg_interactions_to_complete = sum(completed_submissions) / len(completed_submissions) if completed_submissions else 0

    completed_percent = (completed_count / total_students * 100) if total_students > 0 else 0
    attempted_percent = (attempted_count / total_students * 100) if total_students > 0 else 0
    not_started_percent = (not_started_count / total_students * 100) if total_students > 0 else 0

    # JSON rows for Tabulator (frontend)
    student_rows_json = []
    for row in student_data:
        stu = row['student']
        att = row['attempt']
        student_rows_json.append({
            'id': getattr(stu, 'id', None),
            'display_name': getattr(stu, 'get_display_name', lambda: (stu.get_full_name() or getattr(stu, 'username', '') or '').strip())(),
            'attempt_exists': bool(att is not None),
            'attempt_complete': bool(getattr(att, 'complete', False)) if att else False,
            'submissions_count': int(row.get('submissions_count', 0)),
            'hints_count': int(row.get('hints_count', 0)),
        })

    return render(request, 'exercises/teacher/cohort_exercise_detail.html', {
        'selected_cohort': selected_cohort,
        'exercise': exercise,
        'student_data': sorted(student_data, key=lambda x: x['student'].get_full_name() or x['student'].username),
        'student_rows_json': student_rows_json,
        # Stats
        'total_students': total_students,
        'completed_count': completed_count,
        'attempted_count': attempted_count,
        'not_started_count': not_started_count,
        'avg_interactions_to_complete': avg_interactions_to_complete,
        'total_hints': total_hints,
        'total_interactions': total_submissions,
        'completed_percent': completed_percent,
        'attempted_percent': attempted_percent,
        'not_started_percent': not_started_percent,
    })


@login_required
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
        # Assert permission at course scope
        course = get_object_or_404(Course, pk=course_id)
        assert_can_edit_course(request.user, course)
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

        # Assert permission at course scope
        src_module = get_object_or_404(Module, pk=source_module_id)
        src_course_id = src_module.course_id
        tgt_course_id = get_object_or_404(Module, pk=target_module_id).course_id
        if src_course_id != tgt_course_id:
            return JsonResponse({'status': 'error', 'message': 'Source and target modules must belong to the same course'}, status=400)
        assert_can_edit_course(request.user, src_module.course)

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
@require_POST
@transaction.atomic
def set_module_visibility(request, module_id):
    try:
        module = get_object_or_404(Module.objects.select_related('course'), pk=module_id)
        assert_can_edit_course(request.user, module.course)
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
@require_POST
@transaction.atomic
def set_exercise_visibility(request, exercise_id):
    try:
        exercise = get_object_or_404(Exercise.objects.select_related('module__course'), pk=exercise_id)
        assert_can_edit_course(request.user, exercise.module.course)
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
@require_POST
@transaction.atomic
def duplicate_exercise(request, exercise_id):
    try:
        original = get_object_or_404(Exercise.objects.select_related('module__course'), pk=exercise_id)
        assert_can_edit_course(request.user, original.module.course)
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
@require_POST
@transaction.atomic
def delete_exercise(request, exercise_id):
    try:
        exercise = get_object_or_404(Exercise.objects.select_related('module__course'), pk=exercise_id)
        assert_can_edit_course(request.user, exercise.module.course)
        exercise.delete()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
@require_POST
@transaction.atomic
def create_module(request):
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    course_pk = body.get('course_pk')
    name = (body.get('name') or '').strip()
    description = (body.get('description') or '').strip()

    if not course_pk:
        return JsonResponse({'status': 'error', 'message': 'Missing course_pk'}, status=400)
    if not name:
        return JsonResponse({'status': 'error', 'message': 'Missing module name'}, status=400)

    course = get_object_or_404(Course, pk=course_pk)
    assert_can_edit_course(request.user, course)

    # Lock modules of this course to avoid order races
    Module.objects.select_for_update().filter(course=course).values_list('id', flat=True)

    module = Module(
        course=course,
        name=name,
        description=description,
        order=0,  # let the model assign the next order
        visible=True,
    )
    module.save()

    return JsonResponse({'status': 'success', 'module_id': module.id})


@login_required
def exercise_form(request, course_pk, exercise_pk=None, module_pk=None):
    course = get_object_or_404(Course, pk=course_pk)
    assert_can_edit_course(request.user, course)

    # Remember last visited course for teacher dashboard defaulting
    try:
        request.session['last_teacher_course_id'] = course.id
    except Exception:
        pass

    if exercise_pk:  # edit existing exercise
        exercise = get_object_or_404(Exercise, pk=exercise_pk, module__course=course)
    else:  # create new exercise
        if module_pk:
            selected_module = get_object_or_404(Module, pk=module_pk, course=course)
        else:
            selected_module = course.modules.first()  # fallback to first module. should not happen, though
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
            
            # run unit tests (python and scala) and raise an error if any test fails
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
            elif exercise.exercise_type == 'scala' and 'unit_tests' in exercise.answer_data:
                unit_tests = exercise.answer_data_obj.unit_tests.model_dump()
                correct_answers = exercise.answer_data_obj.correct_answers
                for i, correct_answer in enumerate(correct_answers):
                    code_to_test = correct_answer.answer
                    test_results = run_unit_tests_scala(code_to_test, unit_tests)
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
        ExerciseAsset.objects.filter(course=course, name__iendswith='.sql')
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
@require_POST
def exercise_authoring_assistant(request):

    nr.set_background_task(True)     # removes it from web Apdex
    nr.suppress_apdex_metric()       # belt-and-suspenders
    
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
    assert_can_edit_course(request.user, course)

    logger.info("exercise_authoring_assistant called for course_id=%s", getattr(course, 'id', None))

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
            
            has_any = trace_object.traces.filter(channel='authoring').exists()
            if not has_any:
                fields['system_prompt'] = str(result.get('system_prompt') or '')
            
            create_trace_for(trace_object, request.user, channel='authoring', **fields)
        except Exception:
            # Best-effort persistence; do not fail the request on logging errors
            logger.exception("Error persisting authoring interaction as a Trace")
            pass

        return JsonResponse({'status': 'success', **result})
    except Exception as e:
        logger.exception("Error in exercise_authoring_assistant")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

        
@login_required
@require_POST
def translate_i18n(request):
    try:
        body = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    course_pk = body.get('course_pk')
    if not course_pk:
        return JsonResponse({'status': 'error', 'message': 'Missing course_pk in body'}, status=400)
    course = get_object_or_404(Course, pk=course_pk)
    assert_can_edit_course(request.user, course)

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



