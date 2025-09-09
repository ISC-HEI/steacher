from django.core.management.base import BaseCommand
from django.db import transaction

from exercises.models import Attempt, CohortMembership


class Command(BaseCommand):
    help = "Backfill Attempt.cohort for existing attempts based on the user's active cohort in the attempt's course."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Do not persist changes, only report what would change.')
        parser.add_argument('--limit', type=int, default=None, help='Process at most this many attempts (useful for testing).')

    def handle(self, *args, **options):
        dry_run = bool(options.get('dry_run'))
        limit = options.get('limit')

        qs = (
            Attempt.objects
            .select_related('exercise__module__course', 'user')
            .filter(cohort__isnull=True)
            .order_by('id')
        )
        if limit:
            qs = qs[:limit]

        updated = 0
        scanned = 0

        self.stdout.write(self.style.NOTICE(f"Scanning {qs.count()} attempts with null cohort..."))

        @transaction.atomic
        def process_batch():
            nonlocal updated, scanned
            for attempt in qs:
                scanned += 1
                try:
                    course_id = attempt.exercise.module.course_id
                    cm = (
                        CohortMembership.objects
                        .select_related('cohort')
                        .filter(user=attempt.user, status='active', cohort__course_id=course_id)
                        .order_by('-joined_at')
                        .first()
                    )
                    if cm is None:
                        continue
                    if not dry_run:
                        attempt.cohort = cm.cohort
                        attempt.save(update_fields=['cohort', 'updated_at'])
                    updated += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"Skipping attempt {attempt.id} due to error: {e}"))

        process_batch()

        msg = f"Done. Scanned={scanned}, Updated={updated}{' (dry-run)' if dry_run else ''}."
        self.stdout.write(self.style.SUCCESS(msg))


