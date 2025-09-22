
import os
import sys
import json
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max
from exercises.models import Exercise, Attempt
from django.contrib.auth import get_user_model
from exercises.logic import fetch_ai_guidance
import logging

# --- Configuration ---
# This section contains the hard-coded configuration for the script.
ROOT = '/Users/ren/switchdrive/backup/dev/autograder_study'
QUESTION_ID = 7
DB_EXERCISE_ID = 43

# --- Add autograder_study to Python Path ---
# This allows importing the necessary parsing functions directly.
sys.path.append(ROOT)
from parse_student_answers import extract_data_from_html, parse_student_answers

# Set exercises.logic logger to DEBUG for more verbose logging during this command
logging.getLogger('exercises.logic').setLevel(logging.DEBUG)

class Command(BaseCommand):
    help = 'Populates the database with attempts and AI interactions from the autograder study.'

    def handle(self, *args, **options):
        self.stdout.write("Starting to populate attempts from autograder file...")

        # --- Load Student Answers ---
        student_answers_file = os.path.join(
            ROOT,
            "24_25_HES-SO-VS_Informatique_TC-[20242025] Examen semestriel Semesterprüfung-réponses.html"
        )
        if not os.path.exists(student_answers_file):
            self.stderr.write(self.style.ERROR(f"File not found: {student_answers_file}"))
            return

        try:
            df = extract_data_from_html(student_answers_file)
            answers = parse_student_answers(df)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to parse student answers: {e}"))
            return
            
        # --- Find Exercise ---
        try:
            exercise = Exercise.objects.get(id=DB_EXERCISE_ID)
            self.stdout.write(self.style.SUCCESS(f"Found exercise: '{exercise.title}'\n"))
        except Exercise.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Exercise with ID {DB_EXERCISE_ID} not found."))
            return

        # Determine the next version for the attempts, so that we can keep existing attempts
        highest_version = Attempt.objects.filter(exercise=exercise).aggregate(max_version=Max('version'))['max_version']
        next_version = (highest_version or 0) + 1
        self.stdout.write(self.style.SUCCESS(f"Using version {next_version} for new attempts."))

        # Process Each Student
        User = get_user_model()
        for username, student_data in answers.items():
            username = username.replace('@hevs.ch', '').replace('@students.hevs.ch', '')
            
            # Find User
            try:
                user = User.objects.get(username=username)
                self.stdout.write(f"Processing student: {username}")
            except User.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"User '{username}' not found in DB. Skipping."))
                continue

            # Get Answer Text
            answer_text = student_data['answers'].get(QUESTION_ID)
            if not answer_text:
                self.stdout.write(self.style.WARNING(f"No answer found for question {QUESTION_ID} for user '{username}'. Skipping."))
                continue

            # Create Attempt and AttemptInteraction (Transactionally)
            attempt = None
            try:
                # Start a transaction
                with transaction.atomic():
                    # Create the Attempt
                    attempt = Attempt.objects.create(user=user, exercise=exercise, version=next_version, complete=True)
                    
                    # Simulate the user submission for the AI logic
                    data_for_ai = {
                        "action": "run_code",
                        "code": answer_text.strip(),
                        "output": "",
                        "error_message": None,
                    }

                    # Call the AI guidance logic
                    self.stdout.write(f"  Fetching AI guidance for {username}...")
                    llm_response = fetch_ai_guidance(
                        data=data_for_ai,
                        exercise=exercise,
                        attempt=attempt
                    )
                    #print('llm_response: ', llm_response)
                    
                    # The `fetch_ai_guidance` function now handles the creation of the AttemptInteraction,
                    # so we don't need to create it here anymore.

                    self.stdout.write(self.style.SUCCESS(f"  Successfully created Attempt and AttemptInteraction for {username}."))

            except Exception as e:
                # If anything fails, the transaction will be rolled back.
                # If the attempt was created before the transaction scope, we would manually delete it here.
                # But with transaction.atomic(), Django handles it.
                self.stderr.write(self.style.ERROR(f"An error occurred while processing '{username}': {e}"))
                self.stderr.write(self.style.ERROR("Command aborted. No data was saved for this user."))
                # As requested, exit the whole command on failure
                return

        self.stdout.write(self.style.SUCCESS("\nDone. Population of attempts is complete."))
