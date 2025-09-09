from django import template
from django.urls import reverse

from exercises.models import CourseMembership, CohortMembership


register = template.Library()


@register.simple_tag
def teacher_home_url(user):
    """
    Return the appropriate home URL for the top-left logo:
    - Teachers (course owner/editor or cohort owner/teacher) → teachers:dashboard
    - Everyone else → exercises:dashboard
    """
    try:
        if user and getattr(user, 'is_authenticated', False):
            is_course_editor = CourseMembership.objects.filter(
                user=user, role__in=['owner', 'editor']
            ).exists()
            is_cohort_teacher = CohortMembership.objects.filter(
                user=user, role__in=['owner', 'teacher']
            ).exists()
            if is_course_editor or is_cohort_teacher:
                return reverse('teachers:dashboard')
    except Exception:
        pass
    return reverse('exercises:dashboard')


