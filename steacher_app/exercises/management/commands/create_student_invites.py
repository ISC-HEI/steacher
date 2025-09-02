import csv
import os

from django.core.management.base import BaseCommand, CommandError

from exercises.models import StudentInvite


class Command(BaseCommand):
    help = "Create student invites from a CSV file with a column named 'email'. Usage: manage.py create_student_invites path/to/file.csv"

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str, help='Path to CSV file')

    def handle(self, *args, **options):
        path = options['csv_path']
        if not os.path.exists(path):
            raise CommandError(f"File not found: {path}")

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
                obj, was_created = StudentInvite.objects.get_or_create(email=email)
                if was_created:
                    created += 1
                else:
                    skipped += 1

        self.stdout.write(self.style.SUCCESS(f"Invites: created={created}, existing={skipped}"))


