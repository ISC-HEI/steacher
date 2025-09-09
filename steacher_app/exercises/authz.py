from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from .models import CourseMembership, CohortMembership, Course, Cohort, Exercise


def user_is_site_admin(user) -> bool:
    """
    Check if the user is a site admin. In our case, only for `is_superuser`.
    """
    try:
        return bool(user and user.is_authenticated and user.is_superuser)
    except Exception:
        return False


def get_user_course_role(user, course) -> str | None:
    """
    Get the role of the user in the course, through the `CourseMembership` model.
    """
    if not user or not getattr(user, 'is_authenticated', False) or not course:
        return None
    if user_is_site_admin(user):
        return 'owner'
    try:
        membership = CourseMembership.objects.filter(course=course, user=user).only('role').first()
        return membership.role if membership else None
    except Exception:
        return None


def can_view_course(user, course) -> bool:
    """
    Check if the user can view the course.
    Allows: site admin, any course owner/editor/viewer, any cohort member on this course.
    """
    if user_is_site_admin(user):
        return True
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
    Allows: site admin, any course owner/editor/viewer, any cohort member on this course.
    """
    if user_is_site_admin(user):
        return True
    if get_user_course_role(user, exercice.module.course) is not None:
        return True
    if CohortMembership.objects.filter(cohort__course=exercice.module.course, user=user).exists():
        return True
    return False    


def can_edit_course(user, course) -> bool:
    if user_is_site_admin(user):
        return True
    role = get_user_course_role(user, course)
    return role in {'owner', 'editor'}


def get_user_cohort_role(user, cohort) -> str | None:
    if not user or not getattr(user, 'is_authenticated', False) or not cohort:
        return None
    if user_is_site_admin(user):
        return 'owner'
    try:
        membership = CohortMembership.objects.filter(cohort=cohort, user=user).only('role').first()
        return membership.role if membership else None
    except Exception:
        return None


def can_manage_cohort_students(user, cohort) -> bool:
    if user_is_site_admin(user):
        return True
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
    if user_is_site_admin(user):
        return
    role = get_user_cohort_role(user, cohort)
    if role not in {'owner', 'teacher', 'assistant', 'student'}:
        raise PermissionDenied("Forbidden")


def assert_can_manage_cohort(user, cohort):
    if not can_manage_cohort_students(user, cohort):
        raise PermissionDenied("Forbidden")


def course_roles_required(roles=None, *, course_kw='course_pk'):
    """
    Decorator to check if the user has the required role in the course.
    Allows: site admin, any course owner/editor/viewer.
    """
    roles = set(roles or [])

    def decorator(view_func):
        def _wrapped(request, *args, **kwargs):
            course = get_object_or_404(Course, pk=int(kwargs.get(course_kw)))
            if user_is_site_admin(request.user):
                return view_func(request, *args, **kwargs)
            role = get_user_course_role(request.user, course)
            if role in roles:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied("Forbidden")
        return _wrapped
    return decorator


def cohort_roles_required(roles=None, *, cohort_kw='cohort_pk'):
    """
    Decorator to check if the user has the required role in the cohort.
    Allows: site admin, any cohort owner/teacher/assistant/student.
    """
    roles = set(roles or [])

    def decorator(view_func):
        def _wrapped(request, *args, **kwargs):
            cohort = get_object_or_404(Cohort, pk=int(kwargs.get(cohort_kw)))
            if user_is_site_admin(request.user):
                return view_func(request, *args, **kwargs)
            role = get_user_cohort_role(request.user, cohort)
            if role in roles:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied("Forbidden")
        return _wrapped
    return decorator


