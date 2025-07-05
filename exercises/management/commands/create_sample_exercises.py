from django.core.management.base import BaseCommand
from exercises.models import Exercise


class Command(BaseCommand):
    help = 'Create sample multiple choice exercises'

    def handle(self, *args, **options):
        # Clear existing exercises
        Exercise.objects.all().delete()
        
        # Sample multiple choice exercises
        exercises_data = [
            {
                'title': 'Python Basics: Variables',
                'description': 'Test your knowledge of Python variable declarations.',
                'exercise_type': 'multiple_choice',
                'exercise_data': {
                    'question': 'Which of the following is the correct way to declare a variable in Python?',
                    'choices': [
                        {
                            'id': 'a',
                            'text': 'int x = 5',
                            'is_correct': False
                        },
                        {
                            'id': 'b',
                            'text': 'x = 5',
                            'is_correct': True
                        },
                        {
                            'id': 'c',
                            'text': 'var x = 5',
                            'is_correct': False
                        },
                        {
                            'id': 'd',
                            'text': 'declare x = 5',
                            'is_correct': False
                        }
                    ]
                }
            },
            {
                'title': 'JavaScript Functions',
                'description': 'Understanding function syntax in JavaScript.',
                'exercise_type': 'multiple_choice',
                'exercise_data': {
                    'question': 'Which is the correct syntax for defining a function in JavaScript?',
                    'choices': [
                        {
                            'id': 'a',
                            'text': 'function myFunction() {}',
                            'is_correct': True
                        },
                        {
                            'id': 'b',
                            'text': 'def myFunction():',
                            'is_correct': False
                        },
                        {
                            'id': 'c',
                            'text': 'func myFunction() {}',
                            'is_correct': False
                        },
                        {
                            'id': 'd',
                            'text': 'function = myFunction() {}',
                            'is_correct': False
                        }
                    ]
                }
            },
            {
                'title': 'HTML Structure',
                'description': 'Basic HTML document structure knowledge.',
                'exercise_type': 'multiple_choice',
                'exercise_data': {
                    'question': 'Which HTML tag is used to define the main content of a document?',
                    'choices': [
                        {
                            'id': 'a',
                            'text': '<content>',
                            'is_correct': False
                        },
                        {
                            'id': 'b',
                            'text': '<main>',
                            'is_correct': True
                        },
                        {
                            'id': 'c',
                            'text': '<section>',
                            'is_correct': False
                        },
                        {
                            'id': 'd',
                            'text': '<article>',
                            'is_correct': False
                        }
                    ]
                }
            },
            {
                'title': 'CSS Selectors',
                'description': 'Understanding CSS selector syntax.',
                'exercise_type': 'multiple_choice',
                'exercise_data': {
                    'question': 'Which CSS selector targets an element with the class "container"?',
                    'choices': [
                        {
                            'id': 'a',
                            'text': '#container',
                            'is_correct': False
                        },
                        {
                            'id': 'b',
                            'text': '.container',
                            'is_correct': True
                        },
                        {
                            'id': 'c',
                            'text': 'container',
                            'is_correct': False
                        },
                        {
                            'id': 'd',
                            'text': '*container',
                            'is_correct': False
                        }
                    ]
                }
            },
            {
                'title': 'Database Normalization',
                'description': 'Understanding database design principles.',
                'exercise_type': 'multiple_choice',
                'exercise_data': {
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
            }
        ]
        
        # Create exercises
        created_count = 0
        for exercise_data in exercises_data:
            Exercise.objects.create(**exercise_data)
            created_count += 1
            
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created {created_count} sample exercises'
            )
        ) 