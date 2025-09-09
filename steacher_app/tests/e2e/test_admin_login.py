import pytest
from playwright.sync_api import expect
from django.contrib.auth.models import Group, Permission
from exercises.models import Course, ExerciseAsset, Exercise, Trace, Module


def _create_teacher_user(django_user_model):
    """Create a staff 'teacher' user and grant permissions via a Teacher group."""
    # Create a staff "teacher" user
    user = django_user_model.objects.create_user(username="myuser", password="secret", is_staff=True)

    # FIXME also add this on prod db (maybe via mgm command?)
    teacher_group, _ = Group.objects.get_or_create(name="Teacher")
    # Grant all permissions for the exercises app (view/add/change/delete)
    teacher_perms = Permission.objects.filter(content_type__app_label="exercises")
    teacher_group.permissions.set(teacher_perms)
    teacher_group.user_set.add(user)
    return user


def _create_course_and_module(page, live_server, user, course_name):
    """Log in, create a course, a module, and a related asset."""
    page.goto(f"{live_server.url}/admin/")
    page.get_by_label("Username:").fill(user.username)
    page.get_by_label("Password:").fill("secret")
    page.get_by_role("button", name="Log in").click()
    expect(page.get_by_text("Site administration")).to_be_visible()

    # Create course
    page.get_by_role("link", name="Courses").click()
    page.get_by_role("link", name="Add course").click()
    page.get_by_label("Name:").fill(course_name)
    # FIXME add llm prompt for exercice type
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.get_by_role("link", name=course_name, exact=True).first).to_be_visible()

    # Create module
    page.get_by_role("link", name="Modules").click()
    page.get_by_role("link", name="Add module").click()
    # Select the course via native select
    page.get_by_label("Course:").select_option(label=course_name)
    page.get_by_label("Name:").fill("My Test Module")
    page.get_by_label("Description:").fill("My Test Module Description")
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.get_by_role("link", name="My Test Module", exact=True).first).to_be_visible()


def _create_sql_exercise(page, live_server, course_name):
    """Create a new SQL exercise within the specified course."""

    # create an SQL asset for this course so it appears in the exercise form
    course = Course.objects.get(name=course_name)
    sql_content = """CREATE TABLE students (
      first_name VARCHAR,
      last_name VARCHAR,
      city VARCHAR,
      age INTEGER
    );
    INSERT INTO students (first_name, last_name, age) VALUES ('Yoko', 'Tsuno', 23);
    INSERT INTO students (first_name, last_name, age) VALUES ('Raoul', 'Chatigré', 17);"""
    ExerciseAsset.objects.create(
        name="students_v1.sql",
        description="Sample students table with initial data",
        content=sql_content.encode('utf-8'),
        course=course,
    )

    # Navigate to the course page to add an exercise
    page.goto(f"{live_server.url}/teachers/courses/")
    page.get_by_role("link", name=course_name).click()

    # Add a SQL exercise to the module via the form
    page.get_by_role("button", name="Add exercise").click()
    page.get_by_label("Title").fill("List all students")
    page.get_by_label("Exercise Type").select_option(label="SQL")
    page.get_by_label("Question (Markdown supported)").fill("For this first exercise, write an SQL query to list all rows from the `students` table.")
    # Select the SQL asset we created
    page.get_by_label("Database File").select_option(label="students_v1.sql")
    page.get_by_role("button", name="Save Exercise").click()

    # Back on the course page, the new exercise should be listed
    expect(page.get_by_text("List all students").first).to_be_visible()
    return Exercise.objects.get(title="List all students")


def _solve_sql_exercise(page, live_server, user, exercise):
    """Navigate to the exercise page, solve it, and verify completion."""
    # Go to the exercise page to solve it
    page.goto(f"{live_server.url}/exercises/{exercise.id}/")

    # *wait* till the sql engine is ready ("Loading" text is not visible anymore)
    expect(page.get_by_text("Loading database...")).not_to_be_visible()
    # Fill the answer in the CodeMirror editor
    page.locator(".cm-content").fill("SELECT * FROM students;")
    page.get_by_role("button", name="Run Query").click()
    expect(page.get_by_text("2 row(s) returned")).to_be_visible()

    # Ask for a hint to trigger the <exercise_completed> flag and wait for the response.
    with page.expect_response("**/guidance/") as response_info:
        page.get_by_role("button", name="Gimme a Hint").click()
    assert response_info.value.ok, "The request for guidance should succeed."

    # Verify the trace is marked as complete in the database.
    trace = Trace.objects.get(user=user, exercise=exercise)
    trace.refresh_from_db()
    assert trace.complete is True, "The trace should be marked as complete."


@pytest.mark.django_db(transaction=True)
def test_e2e_sql_exercise(live_server, page, django_user_model):
    """
    Test the full E2E workflow for a teacher:
    1. Create user, course, module, database and SQL exercise.
    2. Solve the exercise and verify completion.
    """
    user = _create_teacher_user(django_user_model)
    _create_course_and_module(page, live_server, user, "My SQL Test Course")
    exercise = _create_sql_exercise(page, live_server, "My SQL Test Course")
    _solve_sql_exercise(page, live_server, user, exercise)


def _create_python_exercise(page, live_server, course_name):
    """Create a new Python exercise within the specified course."""
    
     # Navigate to the course page to add an exercise
    page.goto(f"{live_server.url}/teachers/courses/")
    page.get_by_role("link", name=course_name).click()

    # Add a SQL exercise to the module via the form
    page.get_by_role("button", name="Add exercise").click()
    page.get_by_label("Title").fill("Sum of two numbers")
    page.get_by_label("Exercise Type").select_option(label="Python")
    page.get_by_label("Question (Markdown supported)").fill("For this first exercise, write a Python function called `sum_two_numbers` that returns the sum of two numbers.")

    # Add solution, click on "Add solution" button
    page.get_by_role("button", name="Add Correct Answer").click()
    page.get_by_label("Answer", exact=True).fill("def sum_two_numbers(a, b):\n    return a + b")
    
    # Add test cases, click on "Add test case" button
    page.get_by_role("button", name="Add Test Case", exact=True).click()
    # Fill in the first test case
    page.locator("input[id='desc-0']").fill("Test with 12 and 2")
    page.locator("textarea[id='code-0']").fill("print(sum_two_numbers(12, 2))")
    page.locator("textarea[id='output-0']").fill("14")

    page.get_by_role("button", name="Save Exercise").click()

    # Back on the course page, the new exercise should be listed
    expect(page.get_by_text("Sum of two numbers").first).to_be_visible()
    return Exercise.objects.get(title="Sum of two numbers")



def _solve_python_exercise(page, live_server, user, exercise):
    """Navigate to the exercise page, solve it, and verify completion."""
    # Go to the exercise page to solve it
    page.goto(f"{live_server.url}/exercises/{exercise.id}/")

    # Wait until the Python interpreter is ready
    expect(page.get_by_text("Loading Python")).not_to_be_visible()

    # Fill the answer in the CodeMirror editor
    solution_code = "def sum_two_numbers(a, b):\n    return a + b"
    page.locator(".cm-content").fill(solution_code)
    
    page.get_by_role("button", name="Run Code").click()
    
    # Wait for the output to appear to confirm execution
    expect(page.get_by_text("Console Output:")).to_be_visible()
    
    # Verify the trace is marked as complete in the database.
    trace = Trace.objects.get(user=user, exercise=exercise)
    trace.refresh_from_db()
    assert trace.complete is True, "The trace should be marked as complete."


@pytest.mark.django_db(transaction=True)
def test_e2e_python_exercise(live_server, page, django_user_model):
    """
    Test the full E2E workflow for a teacher:
    1. Create user, course, module, database and SQL exercise.
    2. Solve the exercise and verify completion.
    """
    user = _create_teacher_user(django_user_model)
    _create_course_and_module(page, live_server, user, "My Python Test Course")
    exercise = _create_python_exercise(page, live_server, "My Python Test Course")
    _solve_python_exercise(page, live_server, user, exercise)