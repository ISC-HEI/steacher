# Import students from CSV and enroll them in a cohort.
# Supports French or English header names for identity fields.

import csv
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.utils.crypto import get_random_string
from exercises.models import Cohort, CohortMembership

User = get_user_model()


class Command(BaseCommand):
    help = 'Import students from CSV file and add them to the given cohort'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_file',
            type=str,
            help='Path to the CSV file containing student data'
        )
        parser.add_argument(
            'cohort_id',
            type=int,
            help='Cohort ID to enroll students into'
        )
        parser.add_argument(
            'language',
            choices=['fr', 'de', 'en'],
            help='Preferred language for newly created users'
        )

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        cohort_id = options['cohort_id']
        language = options['language']

        # Get target cohort
        try:
            cohort = Cohort.objects.get(id=cohort_id)
            self.stdout.write(self.style.SUCCESS(f"Found cohort: {cohort}"))
        except Cohort.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Cohort with ID {cohort_id} does not exist"))
            return

        created_count = 0
        added_to_cohort_count = 0
        error_count = 0

        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                french_headers = {'Nom', 'Prénom', 'Mail'}
                english_headers = {'last_name', 'first_name', 'email'}

                # Verify expected columns exist (French or English)
                fieldnames = set(reader.fieldnames or [])
                uses_french = french_headers.issubset(fieldnames)
                uses_english = english_headers.issubset(fieldnames)
                if not (uses_french or uses_english):
                    self.stderr.write(self.style.ERROR(
                        "CSV must contain either French headers "
                        "('Nom', 'Prénom', 'Mail') or English headers "
                        "('last_name', 'first_name', 'email'). "
                        f"Found: {reader.fieldnames}"
                    ))
                    return

                for row in reader:
                    if uses_french:
                        last_name = (row.get('Nom') or '').strip()
                        first_name = (row.get('Prénom') or '').strip()
                        email = (row.get('Mail') or '').strip().lower()
                    else:
                        last_name = (row.get('last_name') or '').strip()
                        first_name = (row.get('first_name') or '').strip()
                        email = (row.get('email') or '').strip().lower()

                    if not email:
                        self.stdout.write(self.style.WARNING("Skipping row with empty email") + f" {row}")
                        error_count += 1
                        continue

                    try:
                        # Check if user exists
                        user, created = User.objects.get_or_create(
                            email=email,
                            defaults={
                                'username': email.split('@')[0],
                                'first_name': first_name,
                                'last_name': last_name,
                                'password': make_password(get_random_string(12)),
                                'preferred_language': language
                            }
                        )

                        if created:
                            self.stdout.write(self.style.SUCCESS(
                                f"Created user: {first_name} {last_name} ({email})"
                            ))
                            created_count += 1

                        # Ensure user is in cohort as student
                        _, membership_created = CohortMembership.objects.get_or_create(
                            cohort=cohort,
                            user=user,
                            defaults={
                                'role': 'student',
                                'status': 'active',
                                'added_by': cohort.owner,
                            }
                        )

                        if membership_created:
                            self.stdout.write(self.style.SUCCESS(
                                f"  -> Added to cohort {cohort_id}"
                            ))
                            added_to_cohort_count += 1
                        else:
                            self.stdout.write(self.style.NOTICE(
                                f"  -> Already in cohort {cohort_id}"
                            ))

                    except Exception as e:
                        self.stderr.write(self.style.ERROR(
                            f"Error processing {email}: {e}"
                        ))
                        error_count += 1

        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"File not found: {csv_file}"))
            return
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error reading CSV: {e}"))
            return

        # Summary
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.SUCCESS(f"Import complete!"))
        self.stdout.write(f"  Users created: {created_count}")
        self.stdout.write(f"  Added to cohort {cohort_id}: {added_to_cohort_count}")
        if error_count > 0:
            self.stdout.write(self.style.WARNING(f"  Errors: {error_count}"))
        self.stdout.write("="*60)
