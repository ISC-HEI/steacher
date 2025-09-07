from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exercises', '0006_trace_created_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='trace',
            name='channel',
            field=models.CharField(
                choices=[('exercise_guidance', 'Exercise Guidance'), ('learning_pathway', 'Learning Pathway'), ('authoring', 'Authoring')],
                default='exercise_guidance',
                help_text='Logical stream for this trace (e.g., guidance vs. pathway vs. authoring).',
                max_length=32,
            ),
        ),
        migrations.RemoveConstraint(
            model_name='trace',
            name='unique_trace_rank_per_owner',
        ),
        migrations.AddConstraint(
            model_name='trace',
            constraint=models.UniqueConstraint(
                fields=('content_type', 'object_id', 'channel', 'rank_order'), name='unique_trace_rank_per_owner_channel'
            ),
        ),
        migrations.AddIndex(
            model_name='trace',
            index=models.Index(fields=['content_type', 'object_id', 'channel'], name='trace_ct_oid_channel_idx'),
        ),
    ]


