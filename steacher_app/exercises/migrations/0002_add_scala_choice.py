from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exercises', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='exercise',
            name='exercise_type',
            field=models.CharField(
                choices=[
                    ('python', 'Python'),
                    ('multiple_choice', 'Multiple Choice'),
                    ('sql', 'SQL'),
                    ('turtle', 'Turtle'),
                    ('open_question', 'Open Question'),
                    ('scala', 'Scala'),
                ],
                default='python',
                help_text="Type of the exercice, e.g. 'multiple_choice', 'text', 'turtle', etc.",
                max_length=50,
            ),
        ),
    ]


