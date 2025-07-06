from django.core.management.base import BaseCommand
from exercises.models import Exercise, ExerciceAsset


class Command(BaseCommand):
    help = 'Create sample multiple choice exercises'

    def handle(self, *args, **options):
        # Clear existing exercises and assets
        Exercise.objects.all().delete()
        ExerciceAsset.objects.all().delete()
        
        # Sample multiple choice exercises
        sql_exercises_data =   {
                'title': 'Hello SQL',
                'description': 'Hello world with SQL using minimalisting students db',
                'exercise_type': 'sql',
                'exercise_data': {
                    "question": "Write a query to list all students from the `students` table",
                    "db": "students_v1.sql",
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
          
           
           
           
        
        sql_exercise = Exercise.objects.create(**sql_exercises_data)
        
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
            title='Database Normalization',
            description='Understanding database design principles.',
            exercise_type='multiple_choice',
            exercise_data={
                'question': 'What is the main purpose of database normalization?',
                'choices': [
                    {
                        'id': 'a',
                        'text': 'To increase database size',
                        'is_correct': False
                    },
                    {
                        'id': 'b',
                        'text': 'To reduce data redundancy and improve data integrity',
                        'is_correct': True
                    },
                    {
                        'id': 'c',
                        'text': 'To make queries slower',   
                        'is_correct': False
                    },
                    {
                        'id': 'd',
                        'text': 'To duplicate data across tables',
                        'is_correct': False 
                    }
                ]
            }
        )



    
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created sample exercises and assets'
            )
        ) 