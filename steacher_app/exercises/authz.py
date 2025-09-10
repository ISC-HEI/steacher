from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from .models import CourseMembership, CohortMembership, Course, Cohort, Exercise


def get_user_course_role(user, course) -> str | None:
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


def can_view_course(user, course) -> bool:
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

def can_view_exercise(user, exercice : Exercise):
    """
    Check if the user can view the exercise.
    Allows: any course owner/editor/viewer, any cohort member on this course.
    """
    if get_user_course_role(user, exercice.module.course) is not None:
        return True
    if CohortMembership.objects.filter(cohort__course=exercice.module.course, user=user).exists():
        return True
    return False    


def can_edit_course(user, course) -> bool:
    role = get_user_course_role(user, course)
    return role in {'owner', 'editor'}


def get_user_cohort_role(user, cohort) -> str | None:
    if not user or not getattr(user, 'is_authenticated', False) or not cohort:
        return None
    try:
        membership = CohortMembership.objects.filter(cohort=cohort, user=user).only('role').first()
        return membership.role if membership else None
    except Exception:
        return None


def can_manage_cohort_students(user, cohort) -> bool:
    role = get_user_cohort_role(user, cohort)
    return role in {'owner', 'teacher', 'assistant'}


def assert_can_view_exercise(user, exercise):
    if not can_view_exercise(user, exercise):
        raise PermissionDenied("Forbidden")


def assert_can_view_course(user, course):
    if not can_view_course(user, course):
        raise PermissionDenied("Forbidden")


def assert_can_edit_course(user, course):
    if not can_edit_course(user, course):
        raise PermissionDenied("Forbidden")


def assert_can_view_cohort(user, cohort):
    role = get_user_cohort_role(user, cohort)
    if role not in {'owner', 'teacher', 'assistant', 'student'}:
        raise PermissionDenied("Forbidden")


def assert_can_manage_cohort(user, cohort):
    if not can_manage_cohort_students(user, cohort):
        raise PermissionDenied("Forbidden")


def course_roles_required(roles=None, *, course_kw='course_pk'):
    """
    Decorator to check if the user has the required role in the course.
    Allows: any course owner/editor/viewer.
    """
    roles = set(roles or [])

    def decorator(view_func):
        def _wrapped(request, *args, **kwargs):
            course = get_object_or_404(Course, pk=int(kwargs.get(course_kw)))
            role = get_user_course_role(request.user, course)
            if role in roles:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied("Forbidden")
        return _wrapped
    return decorator


def cohort_roles_required(roles=None, *, cohort_kw='cohort_pk'):
    """
    Decorator to check if the user has the required role in the cohort.
    Allows: any cohort owner/teacher/assistant/student.
    """
    roles = set(roles or [])

    def decorator(view_func):
        def _wrapped(request, *args, **kwargs):
            cohort = get_object_or_404(Cohort, pk=int(kwargs.get(cohort_kw)))
            role = get_user_cohort_role(request.user, cohort)
            if role in roles:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied("Forbidden")
        return _wrapped
    return decorator


