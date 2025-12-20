from django import template
from django.urls import reverse
from exercises.authz import can_edit_any_course


register = template.Library()


@register.simple_tag
def teacher_home_url(user):
    """
    Return the appropriate home URL for the top-left logo:
    - Teachers (course owner/editor or cohort owner/teacher) → teachers:dashboard
    - Everyone else → exercises:dashboard
    """
    if can_edit_any_course(user):
        return reverse('teachers:dashboard')
    return reverse('exercises:dashboard')


@register.filter
def can_author_any_course(user):
    """
    Template filter wrapper for authz.can_edit_any_course().
    Used to show/hide the Import Exercises link in navbar.
    """
    return can_edit_any_course(user)
