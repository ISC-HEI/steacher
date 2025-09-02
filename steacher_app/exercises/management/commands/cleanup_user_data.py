
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from exercises.models import Attempt

class Command(BaseCommand):
    help = (
        'Deletes all attempts and associated interactions for non-admin users. '
        'This is a destructive operation and does not ask for confirmation.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--attempt-version',
            type=int,
            help='Only delete attempts with this specific version number.',
            dest='attempt_version',  # Ensures the option is stored in options['attempt_version']
            default=None
        )

    def handle(self, *args, **options):
        attempt_version = options['attempt_version']

        # 1. Identify non-admin users
        User = get_user_model()
        non_admin_users = User.objects.filter(is_superuser=False, is_staff=False)
        
        if not non_admin_users.exists():
            self.stdout.write(self.style.NOTICE("No non-admin users found. Exiting."))
            return

        self.stdout.write(f"Found {non_admin_users.count()} non-admin users. Starting cleanup...")
        if attempt_version is not None:
            self.stdout.write(self.style.WARNING(f"Only attempts with version {attempt_version} will be deleted."))

        total_attempts_deleted = 0

        # 2. Iterate over each user and delete their attempts
        for user in non_admin_users:
            attempts_to_delete = Attempt.objects.filter(user=user)
            
            # Optionally filter by version
            if attempt_version is not None:
                attempts_to_delete = attempts_to_delete.filter(version=attempt_version)

            user_attempts_count = attempts_to_delete.count()
            if user_attempts_count > 0:
                self.stdout.write(f"  Deleting {user_attempts_count} attempt(s) for user '{user.username}'...")
                
                # As requested, iterate and delete one-by-one
                for attempt in attempts_to_delete:
                    attempt.delete()
                    total_attempts_deleted += 1
            else:
                self.stdout.write(f"  No matching attempts to delete for user '{user.username}'.")
        
        # 3. Provide final feedback
        self.stdout.write(
            self.style.SUCCESS(
                f"\nCleanup complete. A total of {total_attempts_deleted} attempts were deleted."
            )
        )
