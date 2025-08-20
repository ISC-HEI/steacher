from django.db import migrations, models
import django.db.models.deletion


def fill_course_from_exercise(apps, schema_editor):
    ExerciceAsset = apps.get_model('exercises', 'ExerciceAsset')
    Exercise = apps.get_model('exercises', 'Exercise')
    # For each asset, if it was linked to an exercise, copy the exercise's course
    for asset in ExerciceAsset.objects.all():
        exercise_id = getattr(asset, 'exercise_id', None)
        if exercise_id:
            try:
                course_id = Exercise.objects.only('course_id').get(id=exercise_id).course_id
                asset.course_id = course_id
                asset.save(update_fields=['course'])
            except Exercise.DoesNotExist:
                # Leave course as null; will fail later if enforced non-null
                pass


def noop_reverse(apps, schema_editor):
    # No reverse data migration needed
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('exercises', '0005_alter_exercise_exercise_type'),
    ]

    operations = [
        # 1) Add new nullable course FK
        migrations.AddField(
            model_name='exerciceasset',
            name='course',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='assets', to='exercises.course'),
        ),
        # 2) Backfill course from existing exercise relation
        migrations.RunPython(fill_course_from_exercise, noop_reverse),
        # 3) Drop old unique constraint on (name, exercise)
        migrations.RemoveConstraint(
            model_name='exerciceasset',
            name='unique_name_per_exercise',
        ),
        # 4) Remove the exercise FK field
        migrations.RemoveField(
            model_name='exerciceasset',
            name='exercise',
        ),
        # 5) Make course non-nullable
        migrations.AlterField(
            model_name='exerciceasset',
            name='course',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assets', to='exercises.course'),
        ),
        # 6) Add new unique constraint on (name, course)
        migrations.AddConstraint(
            model_name='exerciceasset',
            constraint=models.UniqueConstraint(fields=('name', 'course'), name='unique_name_per_course'),
        ),
    ]


