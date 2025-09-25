from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exercises', '0017_attempt_asked_for_solution'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='system_prompt',
            field=models.TextField(blank=True, help_text='Override the default system prompt used by the AI tutor for exercises in this course. Leave empty to use the global default.'),
        ),
    ]


