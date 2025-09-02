
import os
import json
from django.core.management.base import BaseCommand
from exercises.models import Exercise, Course

class Command(BaseCommand):
    help = 'Imports questions from a JSON file into the database.'

    def handle(self, *args, **options):
        self.stdout.write("Starting to import questions...")

        # --- Configuration ---
        # Path to the JSON file containing the questions.
        # In a real application, you might make this a command-line argument.
        root_path = '/Users/ren/switchdrive/backup/dev/autograder_study'
        json_file_path = os.path.join(root_path, 'quizz.json')

        # Default course name to assign these exercises to.
        # The script will create this course if it doesn't exist.
        default_course_name = "Autograded Python Course"
        
        # --- File and Course Handling ---
        if not os.path.exists(json_file_path):
            self.stderr.write(self.style.ERROR(f"JSON file not found at: {json_file_path}"))
            return

        # Get or create the course
        course, created = Course.objects.get_or_create(name=default_course_name)
        if created:
            self.stdout.write(self.style.SUCCESS(f"Course '{default_course_name}' created."))
        else:
            self.stdout.write(self.style.NOTICE(f"Using existing course: '{default_course_name}'"))

        # --- Load and Process JSON Data ---
        try:
            with open(json_file_path, 'r') as f:
                questions = json.load(f)
        except json.JSONDecodeError:
            self.stderr.write(self.style.ERROR("Invalid JSON. Could not parse the file."))
            return
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error reading file: {e}"))
            return

        # --- Import Questions ---
        created_count = 0
        skipped_count = 0
        for order_str, question_data in questions.items():
            question_name = question_data.get('name')
            question_text = question_data.get('text')
            question_answer = question_data.get('answer')
            order = int(order_str)

            if not all([question_name, question_text, question_answer]):
                self.stdout.write(self.style.WARNING(f"Skipping question at order {order} due to missing data."))
                skipped_count += 1
                continue

            # Check if an exercise with this title already exists in the course
            if Exercise.objects.filter(course=course, title=question_name).exists():
                self.stdout.write(self.style.NOTICE(f"Exercise '{question_name}' already exists. Overwriting."))
                exercise = Exercise.objects.get(course=course, title=question_name)
                # delete the exercise
                exercise.delete()
                

            try:
                Exercise.objects.create(
                    course=course,
                    title=question_name,
                    exercise_type='python',  # Assuming all are Python exercises
                    order=order,
                    exercise_data={
                        'question': question_text
                    },
                    answer_data={
                        'correct_answers': [
                            {
                                'answer': question_answer,
                                'explanation': 'This is the canonical solution.'
                            }
                        ],
                        'expected_result': [],
                        'hints': [],
                        'additional_context': ''
                    }
                )
                self.stdout.write(self.style.SUCCESS(f"Successfully created exercise: '{question_name}'"))
                created_count += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Failed to create exercise '{question_name}': {e}"))

        self.stdout.write(self.style.SUCCESS(f"\nImport complete. Created {created_count} new exercises. Skipped {skipped_count} exercises."))
