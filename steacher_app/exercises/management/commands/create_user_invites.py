import csv
import os

from django.core.management.base import BaseCommand, CommandError

from exercises.models import UserInvite, Cohort


class Command(BaseCommand):
    help = "Create user invites from a CSV file with a column named 'email' and optionally add them to a cohort. Usage: manage.py create_user_invites path/to/file.csv cohort_id"

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str, help='Path to CSV file')
        parser.add_argument('cohort_id', type=int, help='ID of the cohort to add the invites to')

    def handle(self, *args, **options):
        path = options['csv_path']
        cohort_id = options['cohort_id']
        if not os.path.exists(path):
            raise CommandError(f"File not found: {path}")
        if not Cohort.objects.filter(id=cohort_id).exists():
            raise CommandError(f"Cohort not found: {cohort_id}")
        cohort = Cohort.objects.get(id=cohort_id)

        created = 0
        skipped = 0
        with open(path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames or 'email' not in reader.fieldnames:
                raise CommandError("CSV must contain an 'email' header")
            for row in reader:
                email = (row.get('email') or '').strip().lower()
                if not email:
                    continue
                obj, was_created = UserInvite.objects.get_or_create(email=email, defaults={'cohort': cohort})
                if was_created:
                    created += 1
                    self.stdout.write(self.style.SUCCESS(f"Created invite for {email} ({cohort.name})"))
                else:
                    skipped += 1
                    self.stdout.write(self.style.WARNING(f"Skipped invite for {email} ({cohort.name}), already exists"))

        self.stdout.write(self.style.SUCCESS(f"Invites: created={created}, existing={skipped}"))


