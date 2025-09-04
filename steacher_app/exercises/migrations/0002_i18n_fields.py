from django.db import migrations, models


def forwards_copy_to_i18n(apps, schema_editor):
    Exercise = apps.get_model('exercises', 'Exercise')
    for ex in Exercise.objects.all().only('id', 'title_i18n', 'description_i18n', 'exercise_data'):
        # These fields might not exist anymore in the model; use historical fields via _meta if needed
        # Access legacy fields via values() to be safe
        row = Exercise.objects.filter(id=ex.id).values('id').first()
        # Copy title/description into i18n.en if legacy columns exist
        try:
            legacy = Exercise.objects.filter(id=ex.id).values('title', 'description').first() or {}
        except Exception:
            legacy = {}

        title_en = (legacy.get('title') or '').strip() if legacy else ''
        description_en = (legacy.get('description') or '').strip() if legacy else ''

        title_map = dict(ex.title_i18n or {})
        desc_map = dict(ex.description_i18n or {})
        if title_en and not title_map.get('en'):
            title_map['en'] = title_en
        if description_en and not desc_map.get('en'):
            desc_map['en'] = description_en

        # Migrate exercise_data.question -> exercise_data.question_i18n.en
        data = dict(ex.exercise_data or {})
        try:
            q = (data.get('question') or '').strip()
        except Exception:
            q = ''
        if q:
            qi = dict(data.get('question_i18n') or {})
            if not qi.get('en'):
                qi['en'] = q
            data['question_i18n'] = qi
            # remove legacy question
            if 'question' in data:
                del data['question']

        Exercise.objects.filter(id=ex.id).update(title_i18n=title_map, description_i18n=desc_map, exercise_data=data)


def backwards_noop(apps, schema_editor):
    # No-op
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('exercises', '0002_add_scala_choice'),
    ]

    operations = [
        migrations.AddField(
            model_name='exercise',
            name='title_i18n',
            field=models.JSONField(blank=True, default=dict, help_text="Localized title strings by language code, e.g. {'en': '...', 'fr': '...'}"),
        ),
        migrations.AddField(
            model_name='exercise',
            name='description_i18n',
            field=models.JSONField(blank=True, default=dict, help_text="Localized description strings by language code, e.g. {'en': '...', 'fr': '...'}"),
        ),
        migrations.RunPython(forwards_copy_to_i18n, backwards_noop),
        migrations.RemoveField(
            model_name='exercise',
            name='title',
        ),
        migrations.RemoveField(
            model_name='exercise',
            name='description',
        ),
        migrations.AddField(
            model_name='exercise',
            name='question_i18n',
            field=models.JSONField(blank=True, default=dict, help_text="Localized question (Markdown) by language code, e.g. {'en': '...', 'fr': '...'}"),
        ),
    ]


