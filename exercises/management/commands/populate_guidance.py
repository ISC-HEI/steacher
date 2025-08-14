from django.core.management.base import BaseCommand
from exercises.models import Exercise, Trace
from exercises.logic import fetch_ai_guidance
from django.contrib.auth.models import User
import json

class Command(BaseCommand):
    help = 'Populates the database with AI guidance for a specific exercise and user.'

    def add_arguments(self, parser):
        parser.add_argument('exercise_id', type=int, help='The ID of the exercise to populate guidance for.')
        parser.add_argument('user_id', type=int, help='The ID of the user to generate guidance for.')
        parser.add_argument('question', type=str, help='The question to ask the AI.')
        parser.add_argument('--llm_name', type=str, default='gpt-4o', help='The name of the language model to use.')

    def handle(self, *args, **options):
        exercise_id = options['exercise_id']
        user_id = options['user_id']
        question = options['question']
        llm_name = options['llm_name']

        try:
            exercise = Exercise.objects.get(pk=exercise_id)
            user = User.objects.get(pk=user_id)
            trace, _ = Trace.objects.get_or_create(user=user, exercise=exercise)

            data = {
                "action": "ask_question",
                "question": question,
                "llm_name": llm_name,
            }

            self.stdout.write(f"Fetching AI guidance for exercise {exercise_id}, user {user_id}...")
            
            response_data = fetch_ai_guidance(data, exercise, trace)

            self.stdout.write(self.style.SUCCESS('Successfully fetched and stored AI guidance.'))
            self.stdout.write(f"AI Response: {response_data['guidance']}")

        except Exercise.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'Exercise with ID "{exercise_id}" does not exist.'))
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'User with ID "{user_id}" does not exist.'))
        except ValueError as e:
            self.stderr.write(self.style.ERROR(f"A value error occurred: {e}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'An unexpected error occurred: {e}'))
