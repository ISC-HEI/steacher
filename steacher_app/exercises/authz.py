from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from functools import wraps
import logging
import time
import newrelic.agent as nr

from .models import CourseMembership, CohortMembership, Course, Cohort, Exercise
from django.contrib.auth import get_user_model

User = get_user_model()


def get_user_course_role(user: User, course: Course) -> str | None:
    """
    Get the role of the user in the course, through the `CourseMembership` model.
    """
    if not user or not getattr(user, 'is_authenticated', False) or not course:
        return None
    try:
        membership = CourseMembership.objects.filter(course=course, user=user).only('role').first()
        return membership.role if membership else None
    except Exception:
        return None


def can_view_course(user: User, course: Course) -> bool:
    """
    Check if the user can view the course.
    Allows: any course owner/editor/viewer, any cohort member on this course.
    """
    # Course membership: owner/editor/viewer
    role = get_user_course_role(user, course)
    if role in {'owner', 'editor', 'viewer'}:
        return True
    # Cohort membership on this course (any role) also grants course view access
    try:
        return CohortMembership.objects.filter(cohort__course=course, user=user).exists()
    except Exception:
        return False

def can_view_exercise(user: User, exercice: Exercise):
    """
    Check if the user can view the exercise.
    
    Allows:
    - Course owner/editor/viewer: can view ANY exercise (including hidden ones)
    - Cohort member (student): can ONLY view visible exercises
    - Cohort teacher/assistant: can ONLY view visible exercises (same as students)
    """
    course = exercice.module.course
    role = get_user_course_role(user, course)
    
    # Course-level roles (owner/editor/viewer) can view all exercises
    if role in {'owner', 'editor', 'viewer'}:
        return True
    
    # Students and cohort-level teachers can only view visible exercises
    if not exercice.visible:
        return False
    
    # Check if user is a cohort member (any role)
    if CohortMembership.objects.filter(cohort__course=course, user=user).exists():
        return True
    
    return False    


def can_edit_course(user: User, course: Course) -> bool:
    role = get_user_course_role(user, course)
    return role in {'owner', 'editor'}


def get_user_cohort_role(user: User, cohort: Cohort) -> str | None:
    if not user or not getattr(user, 'is_authenticated', False) or not cohort:
        return None
    try:
        membership = CohortMembership.objects.filter(cohort=cohort, user=user).only('role').first()
        return membership.role if membership else None
    except Exception:
        return None


def can_manage_cohort_students(user: User, cohort: Cohort) -> bool:
    role = get_user_cohort_role(user, cohort)
    return role in {'owner', 'teacher', 'assistant'}


def assert_can_view_exercise(user: User, exercise: Exercise):
    if not can_view_exercise(user, exercise):
        raise PermissionDenied("Forbidden")


def assert_can_view_course(user: User, course: Course):
    if not can_view_course(user, course):
        raise PermissionDenied("Forbidden")


def assert_can_edit_course(user: User, course: Course):
    if not can_edit_course(user, course):
        raise PermissionDenied("Forbidden")


def assert_can_view_cohort(user: User, cohort: Cohort):
    role = get_user_cohort_role(user, cohort)
    if role not in {'owner', 'teacher', 'assistant', 'student'}:
        raise PermissionDenied("Forbidden")


def assert_can_manage_cohort(user: User, cohort: Cohort):
    if not can_manage_cohort_students(user, cohort):
        raise PermissionDenied("Forbidden")


def course_roles_required(roles=None, *, course_kw='course_pk'):
    """
    Decorator to check if the user has the required role in the course.
    Allows: any course owner/editor/viewer.
    Attaches `request.course` and `request.course_role` if permission is granted.
    """
    roles: set[str] = set(roles or [])

    def decorator(view_func):
        def _wrapped(request, *args, **kwargs):
            course: Course = get_object_or_404(Course, pk=int(kwargs.get(course_kw)))
            role: str | None = get_user_course_role(request.user, course)
            if role in roles:
                # Attach course to request for the view to use
                request.course = course
                request.course_role = role
                return view_func(request, *args, **kwargs)
            raise PermissionDenied("Forbidden")
        return _wrapped
    return decorator


# ---------------------------------
# Quiz helpers (read-only discovery) TODO refactor and compact these functions
# ---------------------------------

def _quiz_state_for(cohort_id: int, module_id: int) -> dict:
    """Get quiz state from Redis (safe import to avoid cycles)."""
    try:
        from asgiref.sync import async_to_sync
        from .consumers import get_state
        return async_to_sync(get_state)(cohort_id, module_id) or {}
    except Exception:
        return {}


def find_active_quiz_for_user(user: User) -> dict | None:
    """
    Return a lightweight descriptor for the first active quiz (gathering/display_question)
    among the user's ACTIVE cohort memberships. Shape: { 'cohort_id', 'course_name' }.
    Returns None if none is active.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    try:
        memberships = (
            CohortMembership.objects
            .filter(user=user, status='active')
            .select_related('cohort__course')
        )
        for m in memberships:
            course = m.cohort.course
            quiz_modules = course.modules.filter(is_quiz=True, visible=True)
            for mod in quiz_modules:
                state = _quiz_state_for(m.cohort_id, mod.id)
                if (state.get('state') or '') in ('gathering', 'display_question'):
                    return {'cohort_id': m.cohort_id, 'course_name': course.name}
    except Exception:
        return None
    return None


def find_active_quiz_in_course(user: User, course: Course) -> tuple[bool, int | None]:
    """
    Check if the given course has an active quiz for this user (gathering/display_question).
    Returns (has_active_quiz, cohort_id_if_any).
    """
    if not user or not getattr(user, 'is_authenticated', False) or not course:
        return (False, None)
    try:
        memberships = (
            CohortMembership.objects
            .filter(user=user, status='active', cohort__course=course)
            .select_related('cohort')
        )
        quiz_modules = course.modules.filter(is_quiz=True, visible=True)
        for m in memberships:
            for mod in quiz_modules:
                state = _quiz_state_for(m.cohort_id, mod.id)
                if (state.get('state') or '') in ('gathering', 'display_question'):
                    return (True, m.cohort_id)
    except Exception:
        return (False, None)
    return (False, None)


def get_quiz_context_for_course(user: User, course: Course) -> tuple[bool, Cohort | None, int | None]:
    """
    Determine quiz overlay context for an exercise within a course.
    Returns (quiz_mode, cohort_obj, quiz_module_id). quiz_mode is True only when
    state is display_question or results_for_current_question.
    """
    if not user or not getattr(user, 'is_authenticated', False) or not course:
        return (False, None, None)
    try:
        memberships = (
            CohortMembership.objects
            .filter(user=user, status='active', cohort__course=course)
            .select_related('cohort')
        )
        quiz_modules = course.modules.filter(is_quiz=True, visible=True)
        for m in memberships:
            for mod in quiz_modules:
                state = _quiz_state_for(m.cohort_id, mod.id)
                s = (state.get('state') or '')
                if s in ('display_question', 'results_for_current_question'):
                    return (True, m.cohort, mod.id)
        return (False, None, None)
    except Exception:
        return (False, None, None)


def cohort_roles_required(roles=None, *, cohort_kw='cohort_pk'):
    """
    Decorator to check if the user has the required role in the cohort.
    Allows: any cohort owner/teacher/assistant/student.
    Attaches `request.cohort` and `request.cohort_role` if permission is granted.
    """
    roles: set[str] = set(roles or [])

    def decorator(view_func):
        def _wrapped(request, *args, **kwargs):
            pk: str | None = kwargs.get(cohort_kw)
            if not pk:
                raise PermissionDenied("Cohort identifier not found in URL.")
            
            # Fetch cohort and related course once, reducing DB hits.
            cohort: Cohort = get_object_or_404(Cohort.objects.select_related('course'), pk=int(pk))
            
            role: str | None = get_user_cohort_role(request.user, cohort)
            if role in roles:
                request.cohort = cohort  # Attach cohort to request for the view to use
                request.cohort_role = role
                return view_func(request, *args, **kwargs)
            raise PermissionDenied("Forbidden")
        return _wrapped
    return decorator


# ---------------------------------
# Session-backed rate limiting
# ---------------------------------

logger = logging.getLogger(__name__)


WINDOW_SECONDS = 60  # fixed one-minute window


def _client_ip(request) -> str:
    xff = (request.META.get('HTTP_X_FORWARDED_FOR') or '').split(',')[0].strip()
    if xff:
        return xff
    return request.META.get('REMOTE_ADDR') or ''


def _touch_bucket(bucket: list[int], now_ms: int, window_ms: int, max_events: int) -> None:
    # Drop events outside window and trim to a small bound
    cutoff = now_ms - window_ms
    i = 0
    n = len(bucket)
    while i < n and bucket[i] < cutoff:
        i += 1
    if i > 0:
        del bucket[:i]
    # Keep a small cap to prevent unbounded growth
    if len(bucket) > max_events + 5:
        del bucket[: len(bucket) - (max_events + 5)]


def rate_limit(*, user_limit: int | None = None, user_burst: int = 0, ip_limit: int | None = None, ip_burst: int = 0, name: str | None = None):
    """
    Session-backed rate limiting decorator.
    Uses request.session to store small timestamp buckets (epoch ms). Good enough for
    per-user throttling without extra infrastructure. Returns 429 with Retry-After.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            try:
                now_ms = int(time.time() * 1000)
                window_ms = WINDOW_SECONDS * 1000
                # Per-user bucket
                if user_limit is not None and user_limit >= 0:
                    allowed = max(0, int(user_limit) + int(user_burst))
                    uid = getattr(getattr(request, 'user', None), 'id', None)
                    if uid is not None:
                        sess_key = f"rl:{name or view_func.__name__}:u:{uid}:{WINDOW_SECONDS}"
                        bucket = request.session.get(sess_key) or []
                        if not isinstance(bucket, list):
                            bucket = []
                        _touch_bucket(bucket, now_ms, window_ms, allowed)
                        if len(bucket) >= allowed:
                            # Compute Retry-After from the event that will expire first
                            retry_after = 0
                            try:
                                oldest_kept = bucket[-allowed]
                                retry_after = max(0, int((oldest_kept + window_ms - now_ms) / 1000))
                            except Exception:
                                retry_after = int(WINDOW_SECONDS)
                            logger.info("Rate limit hit (user) for %s uid=%s ip=%s", name or view_func.__name__, uid, _client_ip(request))
                            
                            # Record NewRelic custom event for alerting
                            try:
                                nr.record_custom_event('RateLimitExceeded', {
                                    'limit_type': 'user',
                                    'endpoint': name or view_func.__name__,
                                    'user_id': uid,
                                    'ip_address': _client_ip(request),
                                    'limit': user_limit,
                                    'burst': user_burst,
                                    'window_seconds': WINDOW_SECONDS,
                                })
                            except Exception:
                                pass  # Don't fail request if NewRelic recording fails
                            
                            resp = JsonResponse({'status': 'error', 'message': 'Rate limit exceeded'}, status=429)
                            resp['Retry-After'] = str(retry_after)
                            return resp
                        bucket.append(now_ms)
                        request.session[sess_key] = bucket
                        request.session.modified = True

                # Per-IP fallback
                if ip_limit is not None and ip_limit >= 0:
                    allowed2 = max(0, int(ip_limit) + int(ip_burst))
                    window_ms2 = window_ms
                    ip = _client_ip(request) or 'unknown'
                    sess_key2 = f"rl:{name or view_func.__name__}:ip:{ip}:{WINDOW_SECONDS}"
                    bucket2 = request.session.get(sess_key2) or []
                    if not isinstance(bucket2, list):
                        bucket2 = []
                    _touch_bucket(bucket2, now_ms, window_ms2, allowed2)
                    if len(bucket2) >= allowed2:
                        retry_after2 = 0
                        try:
                            oldest_kept2 = bucket2[-allowed2]
                            retry_after2 = max(0, int((oldest_kept2 + window_ms2 - now_ms) / 1000))
                        except Exception:
                            retry_after2 = int(WINDOW_SECONDS)
                        logger.info("Rate limit hit (ip) for %s ip=%s", name or view_func.__name__, ip)
                        
                        # Record NewRelic custom event for alerting
                        try:
                            nr.record_custom_event('RateLimitExceeded', {
                                'limit_type': 'ip',
                                'endpoint': name or view_func.__name__,
                                'ip_address': ip,
                                'limit': ip_limit,
                                'burst': ip_burst,
                                'window_seconds': WINDOW_SECONDS,
                            })
                        except Exception:
                            pass  # Don't fail request if NewRelic recording fails
                        
                        resp2 = JsonResponse({'status': 'error', 'message': 'Rate limit exceeded'}, status=429)
                        resp2['Retry-After'] = str(retry_after2)
                        return resp2
                    bucket2.append(now_ms)
                    request.session[sess_key2] = bucket2
                    request.session.modified = True

                return view_func(request, *args, **kwargs)
            except Exception:
                # Fail-open on limiter errors to avoid breaking core flows
                logger.exception("rate_limit decorator error for %s", name or view_func.__name__)
                return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
