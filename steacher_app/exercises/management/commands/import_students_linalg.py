# Management command to import students from CSV files into cohort 9

import csv
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.utils.crypto import get_random_string
from exercises.models import Cohort, CohortMembership

User = get_user_model()


class Command(BaseCommand):
    help = 'Import students from CSV file and add them to cohort 9'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_file',
            type=str,
            help='Path to the CSV file containing student data'
        )

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        
        # Get cohort 9
        try:
            cohort = Cohort.objects.get(id=9)
            self.stdout.write(self.style.SUCCESS(f"Found cohort: {cohort}"))
        except Cohort.DoesNotExist:
            self.stderr.write(self.style.ERROR("Cohort with ID 9 does not exist"))
            return

        created_count = 0
        updated_count = 0
        added_to_cohort_count = 0
        error_count = 0

        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                # Verify expected columns exist
                if not all(col in reader.fieldnames for col in ['Nom', 'Prénom', 'Mail']):
                    self.stderr.write(self.style.ERROR(
                        f"CSV must contain 'Nom', 'Prénom', and 'Mail' columns. Found: {reader.fieldnames}"
                    ))
                    return

                for row in reader:
                    last_name = row['Nom'].strip()
                    first_name = row['Prénom'].strip()
                    email = row['Mail'].strip()

                    if not email:
                        self.stdout.write(self.style.WARNING(f"Skipping row with empty email, " + row))
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
                                'password': make_password(get_random_string(12))
                            }
                        )

                        if created:
                            self.stdout.write(self.style.SUCCESS(
                                f"Created user: {first_name} {last_name} ({email})"
                            ))
                            created_count += 1
                        else:
                            # Update first/last name if changed
                            updated = False
                            if user.first_name != first_name:
                                user.first_name = first_name
                                updated = True
                            if user.last_name != last_name:
                                user.last_name = last_name
                                updated = True
                            
                            if updated:
                                user.save()
                                self.stdout.write(self.style.NOTICE(
                                    f"Updated name for: {email}"
                                ))
                                updated_count += 1
                            else:
                                self.stdout.write(self.style.NOTICE(
                                    f"User already exists: {email}"
                                ))

                        # Ensure user is in cohort 9 as student
                        membership, membership_created = CohortMembership.objects.get_or_create(
                            cohort=cohort,
                            user=user,
                            defaults={
                                'role': 'student',
                                'status': 'active'
                            }
                        )

                        if membership_created:
                            self.stdout.write(self.style.SUCCESS(
                                f"  → Added to cohort 9"
                            ))
                            added_to_cohort_count += 1
                        else:
                            self.stdout.write(self.style.NOTICE(
                                f"  → Already in cohort 9"
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
        self.stdout.write(f"  Users updated: {updated_count}")
        self.stdout.write(f"  Added to cohort 9: {added_to_cohort_count}")
        if error_count > 0:
            self.stdout.write(self.style.WARNING(f"  Errors: {error_count}"))
        self.stdout.write("="*60)
