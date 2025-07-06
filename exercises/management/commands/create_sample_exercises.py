from django.core.management.base import BaseCommand
from exercises.models import Exercise, ExerciceAsset, Course


class Command(BaseCommand):
    help = 'Create sample multiple choice exercises'

    def handle(self, *args, **options):
        # Clear existing exercises and assets
        Exercise.objects.all().delete()
        ExerciceAsset.objects.all().delete()
        Course.objects.all().delete()
        
        # Create a course
        sql_course = Course.objects.create(
            name='SQL Class',
            description='A course for learning SQL basics.'
        )
        
        # SQL Exercise data
        sql_exercises_data = {
            'course': sql_course,
            'title': 'Hello SQL',
            'description': 'Hello world with SQL using minimalisting students db',
            'exercise_type': 'sql',
            'order': 1,
            'exercise_data': {
                "question": "For this first exercise, write an SQL query to list all students from the `students` table",
                "db": "students_v1.sql"
            },
            'answer_data': {
                "expected_result": [
                    {
                        "first_name": "Yoko",
                        "last_name": "Tsuno",
                        "city": None,
                        "age": 23
                    },
                    {
                        "first_name": "Raoul",
                        "last_name": "Chatigré",
                        "city": None,
                        "age": 17
                    }
                ],
                "correct_answers": [
                    {
                        "answer": "SELECT * FROM students;",
                        "explanation": "This is the most straightforward answer"
                    },
                    {
                        "answer": "SELECT first_name, last_name FROM students;",
                        "explanation": "This works too, but it was not specifically asked to select `first_name` and `last_name`. It's fine because it's the first ever sql query that the students will write"
                    }
                ],
                "hints": [
                    "The command to list all entries from a database table has the form `SELECT * FROM {table name}`"
                ],
                "additional_context": "This is the first ever SQL exercice/command that the students will write. It's kind of the hello world in SQL for them. Focus on getting them on-board, not on details."
            }
        }
           
        # Create SQL exercise
        sql_exercise = Exercise.objects.create(**sql_exercises_data)
        
        # Create associated SQL asset
        sql_content = """CREATE TABLE students
(
  first_name        VARCHAR, 
  last_name         VARCHAR,
  city              VARCHAR,
  age               INTEGER
);

INSERT INTO students (first_name, last_name, age) 
  VALUES ('Yoko', 'Tsuno', 23);

INSERT INTO students (first_name, last_name, age) 
  VALUES ('Raoul', 'Chatigré', 17);"""
                
        ExerciceAsset.objects.create(
            name="students_v1.sql",
            description="Sample students table with initial data",
            content=sql_content.encode('utf-8'),
            exercise=sql_exercise
        )

        # Multiple choice exercise
        Exercise.objects.create(
            course=sql_course,
            title='Database Normalization',
            description='Understanding database design principles.',
            exercise_type='multiple_choice',
            order=2,
            exercise_data={
                'question': 'What is the main purpose of database normalization?',
                'choices': [
                    {
                        'id': 'a',
                        'text': 'To increase database size'
                    },
                    {
                        'id': 'b',
                        'text': 'To reduce data redundancy and improve data integrity'
                    },
                    {
                        'id': 'c',
                        'text': 'To make queries slower'
                    },
                    {
                        'id': 'd',
                        'text': 'To duplicate data across tables'
                    }
                ]
            },
            answer_data={
                'correct_choice': 'b',
                'explanation': 'Database normalization is primarily used to reduce data redundancy and improve data integrity by organizing data efficiently.',
                'choice_explanations': {
                    'a': 'Incorrect - Normalization typically reduces database size by eliminating redundancy',
                    'b': 'Correct - This is the main purpose of normalization',
                    'c': 'Incorrect - Normalization can actually improve query performance in many cases',
                    'd': 'Incorrect - Normalization reduces data duplication, not increases it'
                }
            }
        )


        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created sample course, exercises and assets'
            )
        ) 