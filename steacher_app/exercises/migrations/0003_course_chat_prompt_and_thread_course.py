from django.db import migrations, models
import django.db.models.deletion


def set_thread_course_to_first_course(apps, schema_editor):
    Course = apps.get_model('exercises', 'Course')
    ChatThread = apps.get_model('exercises', 'ChatThread')
    first_course = Course.objects.order_by('id').first()
    if not first_course:
        return
    ChatThread.objects.filter(course__isnull=True).update(course=first_course)


class Migration(migrations.Migration):

    dependencies = [
        ('exercises', '0002_chatthread'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='chat_prompt',
            field=models.TextField(blank=True, help_text='Chatbot-specific instructions for this course.'),
        ),
        migrations.AddField(
            model_name='chatthread',
            name='course',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='chat_threads', to='exercises.course'),
        ),
        migrations.RunPython(set_thread_course_to_first_course, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='chatthread',
            name='course',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_threads', to='exercises.course'),
        ),
    ]


