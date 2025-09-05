from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction

from exercises.models import (
    Course,
    Module,
    Exercise,
    Cohort,
    CohortMembership,
    Attempt,
    AttemptInteraction,
    AttemptEval,
)


class Command(BaseCommand):
    help = "Seed a small demo dataset: users, one course with one module and three exercises, one cohort with memberships, attempts and interactions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete previously seeded demo data before recreating it.",
        )
        parser.add_argument(
            "--course-name",
            type=str,
            default="Test Course",
            help="Course name to create/use for the demo.",
        )
        parser.add_argument(
            "--cohort-name",
            type=str,
            default="Demo Cohort",
            help="Cohort name to create/use for the demo.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        course_name = options["course_name"]
        cohort_name = options["cohort_name"]
        reset = options["reset"]

        # Identifiers (keep consistent for idempotency)
        module_name = "Test Module"
        cohort_code = "DEMO1"
        teacher_username = "teacher_demo"
        student_usernames = [
            ("test_student_one", "Test", "Student One"),
            ("test_student_two", "Test", "Student Two"),
            ("test_student_three", "Test", "Student Three"),
        ]

        User = get_user_model()

        if reset:
            # Best-effort cleanup of prior run
            try:
                course = Course.objects.get(name=course_name)
            except Course.DoesNotExist:
                course = None

            if course:
                # Delete related demo data scoped to this course
                # Attempts/interactions/evals
                AttemptInteraction.objects.filter(attempt__exercise__module__course=course).delete()
                AttemptEval.objects.filter(attempt__exercise__module__course=course).delete()
                Attempt.objects.filter(exercise__module__course=course).delete()

                # Cohorts and memberships
                CohortMembership.objects.filter(cohort__course=course).delete()
                Cohort.objects.filter(course=course, name=cohort_name).delete()

                # Exercises/Module/Course
                Exercise.objects.filter(module__course=course).delete()
                Module.objects.filter(course=course, name=module_name).delete()
                course.delete()

            self.stdout.write(self.style.WARNING("Previous demo data removed."))

        # Users
        teacher, _ = User.objects.get_or_create(
            username=teacher_username,
            defaults={
                "email": "teacher_demo@example.com",
                "first_name": "Teacher",
                "last_name": "Demo",
                "role": "teacher",
                "is_staff": True,
            },
        )

        students = []
        for username, first_name, last_name in student_usernames:
            student, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@example.com",
                    "first_name": first_name,
                    "last_name": last_name,
                    "role": "student",
                    "is_staff": False,
                },
            )
            students.append(student)

        # Course and module
        course, _ = Course.objects.get_or_create(
            name=course_name,
            defaults={
                "description": "Seeded demo course",
                "llm_prompts": {"python": ""},
                "visible": True,
            },
        )

        module, _ = Module.objects.get_or_create(
            course=course,
            name=module_name,
            defaults={
                "description": "Seeded demo module",
                "order": 1,
                "visible": True,
            },
        )

        # Three exercises all titled "test" with different orders
        exercises = []
        questions = [
            "Print 'Hello, World!'",
            "Add two numbers and print the result",
            "Loop from 1 to 3 and print each number",
        ]
        for idx, q in enumerate(questions, start=1):
            ex, created = Exercise.objects.get_or_create(
                module=module,
                order=idx,
                defaults={
                    "title_i18n": {"en": f"test{idx}"},
                    "description_i18n": {"en": "Seeded demo exercise"},
                    "exercise_type": "python",
                    "question_i18n": {"en": q},
                    "answer_data": {"hints": [""]},
                    "visible": True,
                },
            )
            # Ensure title and minimal answer_data exist even without --reset
            needs_save = False
            desired_title = f"test{idx}"
            if ex.title != desired_title:
                ex.title_i18n = {"en": desired_title}
                needs_save = True
            if not isinstance(ex.answer_data, dict) or "hints" not in ex.answer_data:
                ex.answer_data = {"hints": [""]}
                needs_save = True
            if needs_save:
                ex.save(update_fields=["title_i18n", "answer_data"])  # safe even if some unchanged
            exercises.append(ex)

        # Cohort and memberships
        cohort, _ = Cohort.objects.get_or_create(
            course=course,
            name=cohort_name,
            defaults={
                "owner": teacher,
                "description": "Seeded demo cohort",
                "code": cohort_code,
            },
        )

        for s in students:
            CohortMembership.objects.get_or_create(cohort=cohort, student=s, defaults={"added_by": teacher})

        # Attempts and interactions
        # student_one -> exercise 1 (complete)
        # student_two -> exercise 1 (complete) and 2 (incomplete)
        # student_three -> exercise 3 (incomplete)
        student_one, student_two, student_three = students

        a1, _ = Attempt.objects.get_or_create(
            exercise=exercises[0], user=student_one, version=1,
            defaults={"complete": True, "cohort": cohort}
        )
        a1.cohort = cohort
        a1.save(update_fields=["cohort"])

        a2, _ = Attempt.objects.get_or_create(
            exercise=exercises[0], user=student_two, version=1,
            defaults={"complete": True, "cohort": cohort}
        )
        a2.cohort = cohort
        a2.save(update_fields=["cohort"])

        a3, _ = Attempt.objects.get_or_create(
            exercise=exercises[1], user=student_two, version=1,
            defaults={"complete": False, "cohort": cohort}
        )
        a3.cohort = cohort
        a3.save(update_fields=["cohort"])

        a4, _ = Attempt.objects.get_or_create(
            exercise=exercises[2], user=student_three, version=1,
            defaults={"complete": False, "cohort": cohort}
        )
        a4.cohort = cohort
        a4.save(update_fields=["cohort"])

        # Add one simple interaction per attempt
        def add_interaction(attempt, user_code, assistant_msg, action="run_code"):
            AttemptInteraction.objects.get_or_create(
                attempt=attempt,
                interaction={
                    "user_submission": {
                        "role": "user",
                        "content": f"I ran this code:\n```python\n{user_code}\n```",
                        "metadata": {"action": action, "code": user_code},
                    },
                    "llm_response": {
                        "role": "assistant",
                        "content": assistant_msg,
                    },
                },
            )

        add_interaction(a1, "print('Hello, World!')", "Looks good! <exercise_completed>")
        add_interaction(a2, "print('Hello, World!')", "Nice, that matches the expected output. <exercise_completed>")
        add_interaction(a3, "print(1 + 2)", "Try formatting the output to match requirements.")
        add_interaction(a4, "for i in range(1, 4):\n    print(i)", "Good start; consider edge cases.")

        # Optional: one evaluation set to OK on a1
        AttemptEval.objects.get_or_create(attempt=a1, defaults={"is_ok": True, "feedback": "Seeded OK"})

        # Summary output
        self.stdout.write(self.style.SUCCESS("Demo data ready:"))
        self.stdout.write(f"- Course: {course.name}")
        self.stdout.write(f"- Module: {module.name}")
        self.stdout.write("- Exercises: 3 titled 'test' with orders 1..3")
        self.stdout.write(f"- Cohort: {cohort.name} (code {cohort.code})")
        self.stdout.write(f"- Teacher: {teacher.username}")
        self.stdout.write("- Students: " + ", ".join(s.username for s in students))
        self.stdout.write("- Attempts created: 4 with simple interactions (some complete)")


