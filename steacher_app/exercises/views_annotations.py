# Annotation views for manual attempt evaluation
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_http_methods

from .authz import assert_can_edit_course
from .models import Exercise, Attempt, AttemptEval


def _get_first_unannotated_attempt(exercise, annotator):
    """
    Returns the first attempt for this exercise that:
    - Has at least one trace
    - Has not been annotated by this annotator
    - Ordered by attempt.id
    """
    return (
        Attempt.objects
        .filter(
            exercise=exercise,
            traces__isnull=False
        )
        .exclude(
            evaluations__annotator=annotator
        )
        .distinct()
        .order_by('id')
        .first()
    )


def _get_next_unannotated_attempt(exercise, current_attempt, annotator):
    """
    Returns the next attempt for this exercise that:
    - Has at least one trace
    - Has not been annotated by this annotator
    - Comes after current_attempt
    - Ordered by attempt.id
    """
    return (
        Attempt.objects
        .filter(
            exercise=exercise,
            traces__isnull=False,
            id__gt=current_attempt.id
        )
        .exclude(
            evaluations__annotator=annotator
        )
        .distinct()
        .order_by('id')
        .first()
    )


def _get_navigation_ids(exercise, current_attempt, annotator):
    """
    Calculate previous, next, and next unannotated attempt IDs for navigation.
    """
    # Get all attempts with traces for this exercise, ordered
    all_attempts = list(
        Attempt.objects
        .filter(
            exercise=exercise,
            traces__isnull=False
        )
        .distinct()
        .order_by('id')
        .values_list('id', flat=True)
    )
    
    if not all_attempts:
        return None, None, None
    
    try:
        current_idx = all_attempts.index(current_attempt.id)
    except ValueError:
        return None, None, None
    
    # Previous and next in the full list
    previous_id = all_attempts[current_idx - 1] if current_idx > 0 else None
    next_id = all_attempts[current_idx + 1] if current_idx < len(all_attempts) - 1 else None
    
    # Next unannotated
    next_unannotated = _get_next_unannotated_attempt(exercise, current_attempt, annotator)
    next_unannotated_id = next_unannotated.id if next_unannotated else None
    
    return previous_id, next_id, next_unannotated_id


@login_required
def annotate_exercise_entry(request, exercise_id):
    """
    Entry point for annotation: finds first unannotated attempt and redirects.
    """
    exercise = get_object_or_404(Exercise.objects.select_related('module__course'), pk=exercise_id)
    course = exercise.module.course
    
    # Check permissions
    assert_can_edit_course(request.user, course)
    
    # Find first unannotated attempt
    first_unannotated = _get_first_unannotated_attempt(exercise, request.user)
    
    if first_unannotated:
        return redirect('teachers:annotate_attempt', exercise_id=exercise_id, attempt_id=first_unannotated.id)
    
    # All annotated - go to first attempt (allow re-annotation)
    first = (
        Attempt.objects
        .filter(exercise=exercise, traces__isnull=False)
        .distinct()
        .order_by('id')
        .first()
    )
    
    if first:
        return redirect('teachers:annotate_attempt', exercise_id=exercise_id, attempt_id=first.id)
    
    # No attempts at all
    messages.info(request, "No attempts to annotate for this exercise.")
    return redirect('teachers:course_detail', pk=course.id)


@login_required
@require_http_methods(["GET", "POST"])
def annotate_attempt(request, exercise_id, attempt_id):
    """
    Main annotation view: display attempt with traces and allow evaluation.
    """
    # Fetch related data
    exercise = get_object_or_404(
        Exercise.objects.select_related('module__course'),
        pk=exercise_id
    )
    attempt = get_object_or_404(
        Attempt.objects.select_related('user', 'cohort'),
        pk=attempt_id,
        exercise=exercise
    )
    course = exercise.module.course
    
    # Check permissions
    assert_can_edit_course(request.user, course)
    
    # Handle POST (save evaluation)
    if request.method == 'POST':
        is_ok_raw = request.POST.get('is_ok')
        feedback = request.POST.get('feedback', '').strip()
        
        # Convert radio button value to Boolean or None
        if is_ok_raw == 'good':
            is_ok = True
        elif is_ok_raw == 'bad':
            is_ok = False
        else:
            is_ok = None
        
        # Save or update evaluation
        AttemptEval.objects.update_or_create(
            attempt=attempt,
            annotator=request.user,
            defaults={
                'is_ok': is_ok,
                'feedback': feedback,
            }
        )
        
        # Determine where to redirect based on which button was clicked
        action = request.POST.get('action', 'next_unannotated')
        
        # Get navigation IDs
        previous_id, next_id, next_unannotated_id = _get_navigation_ids(exercise, attempt, request.user)
        
        if action == 'previous' and previous_id:
            return redirect('teachers:annotate_attempt', exercise_id=exercise_id, attempt_id=previous_id)
        elif action == 'next' and next_id:
            return redirect('teachers:annotate_attempt', exercise_id=exercise_id, attempt_id=next_id)
        elif action == 'next_unannotated' and next_unannotated_id:
            return redirect('teachers:annotate_attempt', exercise_id=exercise_id, attempt_id=next_unannotated_id)
        else:
            # No more to navigate to - stay on current page
            messages.success(request, "Evaluation saved. All attempts annotated!")
            return redirect('teachers:annotate_attempt', exercise_id=exercise_id, attempt_id=attempt_id)
    
    # GET: Display annotation form
    
    # Get traces for this attempt, ordered chronologically
    traces = list(
        attempt.traces
        .filter(channel='exercise_guidance')
        .order_by('rank_order')
    )
    
    # Check for existing evaluation by this annotator
    existing_eval = AttemptEval.objects.filter(
        attempt=attempt,
        annotator=request.user
    ).first()
    
    # Calculate navigation IDs
    previous_id, next_id, next_unannotated_id = _get_navigation_ids(exercise, attempt, request.user)
    
    # Count total and annotated attempts
    total_count = (
        Attempt.objects
        .filter(exercise=exercise, traces__isnull=False)
        .distinct()
        .count()
    )
    annotated_count = (
        Attempt.objects
        .filter(
            exercise=exercise,
            traces__isnull=False,
            evaluations__annotator=request.user
        )
        .distinct()
        .count()
    )
    
    all_done = (next_unannotated_id is None)
    
    context = {
        'exercise': exercise,
        'attempt': attempt,
        'traces': traces,
        'existing_eval': existing_eval,
        'nav': {
            'previous_id': previous_id,
            'next_id': next_id,
            'next_unannotated_id': next_unannotated_id,
            'total_count': total_count,
            'annotated_count': annotated_count,
        },
        'all_done': all_done,
    }
    
    return render(request, 'exercises/teacher/annotate_attempt.html', context)

