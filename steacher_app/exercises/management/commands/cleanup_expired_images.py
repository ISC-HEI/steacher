# Management command to delete orphaned image upload tokens
from django.core.management.base import BaseCommand
from django.utils import timezone
from exercises.models import TraceImage


class Command(BaseCommand):
    help = (
        'Deletes orphaned TraceImage records: expired upload tokens '
        'where no image was ever uploaded.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        now = timezone.now()
        dry_run = options['dry_run']

        # Only delete expired tokens that were never linked to a trace
        orphaned_tokens = TraceImage.objects.filter(
            token_expires_at__lt=now,
            trace__isnull=True
        )

        count = orphaned_tokens.count()

        if count == 0:
            self.stdout.write(self.style.NOTICE("No orphaned tokens found."))
            return

        action = "Would delete" if dry_run else "Deleting"
        self.stdout.write(f"{action} {count} orphaned token(s)...")

        if dry_run:
            # Show details of what would be deleted
            for img in orphaned_tokens[:10]:  # Show first 10
                expired_mins = int((now - img.token_expires_at).total_seconds() / 60)
                self.stdout.write(
                    f"  - Token {img.upload_token[:16]}... "
                    f"(expired {expired_mins}m ago)"
                )
            if count > 10:
                self.stdout.write(f"  ... and {count - 10} more")
            self.stdout.write(self.style.WARNING("\nDry run - no deletions performed."))
        else:
            # Perform deletion
            deleted_count, _ = orphaned_tokens.delete()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully deleted {deleted_count} orphaned token(s)."
                )
            )

