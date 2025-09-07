from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exercises', '0007_trace_channel'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trace',
            name='channel',
            field=models.CharField(
                choices=[('exercise_guidance', 'Exercise Guidance'), ('learning_pathway', 'Learning Pathway'), ('authoring', 'Authoring'), ('study_chat', 'Study Chat')],
                default='exercise_guidance',
                help_text='Logical stream for this trace (e.g., guidance vs. pathway vs. authoring).',
                max_length=32,
            ),
        ),
    ]


