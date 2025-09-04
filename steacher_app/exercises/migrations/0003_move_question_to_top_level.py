from django.db import migrations


def forwards_move_question(apps, schema_editor):
    Exercise = apps.get_model('exercises', 'Exercise')
    for ex in Exercise.objects.all().only('id', 'exercise_data', 'question_i18n'):
        data = dict(ex.exercise_data or {})
        qi_top = dict(getattr(ex, 'question_i18n', {}) or {})
        try:
            # Prefer i18n in exercise_data if present
            qi_nested = data.get('question_i18n') if isinstance(data, dict) else None
            if isinstance(qi_nested, dict):
                for k, v in qi_nested.items():
                    if k not in qi_top and (v or '').strip():
                        qi_top[k] = v
            legacy_q = (data.get('question') or '').strip()
            if legacy_q and 'en' not in qi_top:
                qi_top['en'] = legacy_q
        except Exception:
            pass

        if isinstance(data, dict):
            data.pop('question', None)
            data.pop('question_i18n', None)
        Exercise.objects.filter(id=ex.id).update(exercise_data=data, question_i18n=qi_top)


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('exercises', '0002_i18n_fields'),
    ]

    operations = [
        migrations.RunPython(forwards_move_question, backwards_noop),
    ]


