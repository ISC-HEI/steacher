"""Tests for exercise visibility authorization."""
import pytest
from django.contrib.auth import get_user_model
from exercises.models import Course, Module, Exercise, CourseMembership, Cohort, CohortMembership
from exercises.authz import can_view_exercise

User = get_user_model()


@pytest.fixture
def course():
    """Create a test course."""
    return Course.objects.create(name="Test Course", visible=True)


@pytest.fixture
def module(course):
    """Create a test module."""
    return Module.objects.create(course=course, name="Test Module", order=1, visible=True)


@pytest.fixture
def visible_exercise(module):
    """Create a visible exercise."""
    return Exercise.objects.create(
        module=module,
        title_i18n={"en": "Visible Exercise"},
        exercise_type="python",
        order=1,
        exercise_data={},
        answer_data={},
        visible=True
    )


@pytest.fixture
def hidden_exercise(module):
    """Create a hidden exercise."""
    return Exercise.objects.create(
        module=module,
        title_i18n={"en": "Hidden Exercise"},
        exercise_type="python",
        order=2,
        exercise_data={},
        answer_data={},
        visible=False
    )


@pytest.fixture
def cohort(course):
    """Create a test cohort."""
    return Cohort.objects.create(course=course, name="Test Cohort")


@pytest.fixture
def student_user():
    """Create a student user."""
    return User.objects.create_user(username="student@test.com", password="test123")


@pytest.fixture
def teacher_user():
    """Create a teacher user."""
    return User.objects.create_user(username="teacher@test.com", password="test123")


@pytest.fixture
def editor_user():
    """Create an editor user."""
    return User.objects.create_user(username="editor@test.com", password="test123")


@pytest.fixture
def viewer_user():
    """Create a viewer user."""
    return User.objects.create_user(username="viewer@test.com", password="test123")


@pytest.fixture
def cohort_teacher_user():
    """Create a cohort teacher user."""
    return User.objects.create_user(username="cohort_teacher@test.com", password="test123")


@pytest.mark.django_db
class TestExerciseVisibility:
    """Test exercise visibility authorization logic."""

    def test_student_can_view_visible_exercise(self, student_user, cohort, visible_exercise):
        """Students should be able to view visible exercises."""
        CohortMembership.objects.create(user=student_user, cohort=cohort, role='student', status='active')
        assert can_view_exercise(student_user, visible_exercise) is True

    def test_student_cannot_view_hidden_exercise(self, student_user, cohort, hidden_exercise):
        """Students should NOT be able to view hidden exercises."""
        CohortMembership.objects.create(user=student_user, cohort=cohort, role='student', status='active')
        assert can_view_exercise(student_user, hidden_exercise) is False

    def test_course_owner_can_view_hidden_exercise(self, teacher_user, course, hidden_exercise):
        """Course owners should be able to view hidden exercises."""
        CourseMembership.objects.create(user=teacher_user, course=course, role='owner')
        assert can_view_exercise(teacher_user, hidden_exercise) is True

    def test_course_editor_can_view_hidden_exercise(self, editor_user, course, hidden_exercise):
        """Course editors should be able to view hidden exercises."""
        CourseMembership.objects.create(user=editor_user, course=course, role='editor')
        assert can_view_exercise(editor_user, hidden_exercise) is True

    def test_course_viewer_can_view_hidden_exercise(self, viewer_user, course, hidden_exercise):
        """Course viewers should be able to view hidden exercises."""
        CourseMembership.objects.create(user=viewer_user, course=course, role='viewer')
        assert can_view_exercise(viewer_user, hidden_exercise) is True

    def test_cohort_teacher_cannot_view_hidden_exercise(self, cohort_teacher_user, cohort, hidden_exercise):
        """Cohort teachers should NOT be able to view hidden exercises (only course-level roles can)."""
        CohortMembership.objects.create(user=cohort_teacher_user, cohort=cohort, role='teacher', status='active')
        assert can_view_exercise(cohort_teacher_user, hidden_exercise) is False

    def test_cohort_teacher_can_view_visible_exercise(self, cohort_teacher_user, cohort, visible_exercise):
        """Cohort teachers should be able to view visible exercises."""
        CohortMembership.objects.create(user=cohort_teacher_user, cohort=cohort, role='teacher', status='active')
        assert can_view_exercise(cohort_teacher_user, visible_exercise) is True

    def test_cohort_assistant_cannot_view_hidden_exercise(self, student_user, cohort, hidden_exercise):
        """Cohort assistants should NOT be able to view hidden exercises."""
        CohortMembership.objects.create(user=student_user, cohort=cohort, role='assistant', status='active')
        assert can_view_exercise(student_user, hidden_exercise) is False

    def test_no_membership_cannot_view_any_exercise(self, student_user, visible_exercise, hidden_exercise):
        """Users without any membership should not be able to view any exercise."""
        assert can_view_exercise(student_user, visible_exercise) is False
        assert can_view_exercise(student_user, hidden_exercise) is False

    def test_course_level_trumps_cohort_level(self, editor_user, course, cohort, hidden_exercise):
        """Course-level roles should allow viewing hidden exercises even if user is also a cohort student."""
        CourseMembership.objects.create(user=editor_user, course=course, role='editor')
        CohortMembership.objects.create(user=editor_user, cohort=cohort, role='student', status='active')
        assert can_view_exercise(editor_user, hidden_exercise) is True

