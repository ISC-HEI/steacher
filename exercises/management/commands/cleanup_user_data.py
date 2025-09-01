
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from exercises.models import Trace

class Command(BaseCommand):
    help = (
        'Deletes all traces and associated guidance logs for non-admin users. '
        'This is a destructive operation and does not ask for confirmation.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--trace-version',
            type=int,
            help='Only delete traces with this specific version number.',
            dest='trace_version',  # Ensures the option is stored in options['trace_version']
            default=None
        )

    def handle(self, *args, **options):
        trace_version = options['trace_version']

        # 1. Identify non-admin users
        User = get_user_model()
        non_admin_users = User.objects.filter(is_superuser=False, is_staff=False)
        
        if not non_admin_users.exists():
            self.stdout.write(self.style.NOTICE("No non-admin users found. Exiting."))
            return

        self.stdout.write(f"Found {non_admin_users.count()} non-admin users. Starting cleanup...")
        if trace_version is not None:
            self.stdout.write(self.style.WARNING(f"Only traces with version {trace_version} will be deleted."))

        total_traces_deleted = 0

        # 2. Iterate over each user and delete their traces
        for user in non_admin_users:
            traces_to_delete = Trace.objects.filter(user=user)
            
            # Optionally filter by version
            if trace_version is not None:
                traces_to_delete = traces_to_delete.filter(version=trace_version)

            user_traces_count = traces_to_delete.count()
            if user_traces_count > 0:
                self.stdout.write(f"  Deleting {user_traces_count} trace(s) for user '{user.username}'...")
                
                # As requested, iterate and delete one-by-one
                for trace in traces_to_delete:
                    trace.delete()
                    total_traces_deleted += 1
            else:
                self.stdout.write(f"  No matching traces to delete for user '{user.username}'.")
        
        # 3. Provide final feedback
        self.stdout.write(
            self.style.SUCCESS(
                f"\nCleanup complete. A total of {total_traces_deleted} traces were deleted."
            )
        )
