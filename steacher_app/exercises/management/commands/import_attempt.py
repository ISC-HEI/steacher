import os
import json
import ast
import time
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from exercises.models import Attempt, Trace, TraceImage, Exercise, Cohort
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

class Command(BaseCommand):
    help = 'Imports a single attempt (with traces and images) from a JSON file.'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the attempt JSON file to import')
        parser.add_argument('--dry-run', action='store_true', help='Validate and preview import without writing to the database')

    def handle(self, *args, **options):
        file_path = options.get('file_path')
        dry_run = options.get('dry_run')
        if not file_path or not os.path.exists(file_path):
            raise CommandError('You must specify a valid file path.')

        self.stdout.write(f"Importing Attempt from: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except Exception as e:
                raise CommandError(f"Failed to load JSON: {e}")

        if 'attempts' not in data or not data['attempts']:
            raise CommandError('No attempt data found in file.')
        attempt_json = data['attempts'][0]

        # Validate references
        missing_refs = []
        exercise = Exercise.objects.filter(id=attempt_json['exercise']).first()
        if not exercise:
            missing_refs.append(f"Exercise ID {attempt_json['exercise']} not found.")
        user_model = get_user_model()
        user = user_model.objects.filter(id=attempt_json['user']).first()
        if not user:
            missing_refs.append(f"User ID {attempt_json['user']} not found.")
        cohort = None
        if attempt_json.get('cohort'):
            cohort = Cohort.objects.filter(id=attempt_json['cohort']).first()
            if not cohort:
                missing_refs.append(f"Cohort ID {attempt_json['cohort']} not found.")

        if missing_refs:
            self.stdout.write(self.style.WARNING("Missing references detected:"))
            for ref in missing_refs:
                self.stdout.write(self.style.WARNING(f"  - {ref}"))
            confirm = input("Continue with import (missing references will be set to null)? [y/N]: ")
            if confirm.lower() != 'y':
                self.stdout.write("Import cancelled.")
                return

        # Check for existing attempt
        existing = Attempt.objects.filter(user=user, exercise=exercise, version=attempt_json['version']).first()
        if existing:
            self.stdout.write(self.style.WARNING(f"Attempt for user {getattr(user, 'id', None)}, exercise {getattr(exercise, 'id', None)}, version {attempt_json['version']} already exists. Skipping import."))
            return

        # Dry run summary
        self.stdout.write("\nImport Summary:")
        self.stdout.write(f"  Attempt: user={getattr(user, 'id', None)}, exercise={getattr(exercise, 'id', None)}, cohort={getattr(cohort, 'id', None) if cohort else None}")
        self.stdout.write(f"  Traces: {len(attempt_json['traces'])}")
        total_images = sum(len(trace.get('images', [])) for trace in attempt_json['traces'])
        self.stdout.write(f"  TraceImages: {total_images}")
        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run complete. No changes made."))
            return

        # Import all in a transaction
        try:
            # Generate timestamp-based prefix for upload tokens
            import_timestamp = int(time.time())
            token_counter = 0
            
            with transaction.atomic():
                attempt = Attempt.objects.create(
                    exercise=exercise,
                    user=user,
                    cohort=cohort,
                    complete=attempt_json['complete'],
                    asked_for_solution=attempt_json['asked_for_solution'],
                    version=attempt_json['version'],
                    created_at=attempt_json['created_at'],
                    updated_at=attempt_json['updated_at']
                )
                trace_count = 0
                image_count = 0
                for trace_json in attempt_json['traces']:
                    # Parse content_type string to ContentType instance
                    ct_instance = None
                    ct_str = trace_json.get('content_type', "")
                    if ct_str:
                        # Expecting format like 'app_label | model' or 'app_label.model'
                        if '|' in ct_str:
                            parts = [p.strip() for p in ct_str.split('|')]
                            if len(parts) == 2:
                                app_label, model = parts
                                ct_instance = ContentType.objects.filter(app_label=app_label.lower(), model=model.lower()).first()
                        elif '.' in ct_str:
                            app_label, model = ct_str.split('.', 1)
                            ct_instance = ContentType.objects.filter(app_label=app_label.lower(), model=model.lower()).first()
                    trace = Trace.objects.create(
                        user=user_model.objects.filter(id=trace_json['user']).first() or user,
                        content_object=attempt,
                        channel=trace_json['channel'],
                        system_prompt=trace_json['system_prompt'],
                        assistant_content=trace_json['assistant_content'],
                        assistant_metadata=trace_json['assistant_metadata'],
                        user_content=trace_json['user_content'],
                        user_metadata=trace_json['user_metadata'],
                        rank_order=trace_json['rank_order'],
                        created_at=trace_json['created_at'],
                        object_id=trace_json.get('object', None),
                        content_type=ct_instance
                    )
                    trace_count += 1
                    for image_json in trace_json.get('images', []):
                        # Generate unique upload token with timestamp and counter
                        upload_token = f"import_{import_timestamp}_{token_counter}"
                        token_counter += 1
                        
                        # Generate next_token if one exists in the data
                        next_token = None
                        if image_json.get('next_token'):
                            next_token = f"import_{import_timestamp}_{token_counter}"
                            token_counter += 1
                        
                        TraceImage.objects.create(
                            trace=trace,
                            image=ast.literal_eval(image_json['image']) if image_json['image'] else b'',
                            upload_token=upload_token,
                            token_expires_at=image_json.get('token_expires_at', None),
                            next_token=next_token,
                            image_type=image_json.get('image_type', ""),
                            file_size=image_json.get('file_size', 0),
                            chain_position=image_json.get('chain_position', 0),
                            uploaded_at=image_json.get('uploaded_at', None),
                            created_at=image_json.get('created_at', None)
                        )
                        image_count += 1
                self.stdout.write(self.style.SUCCESS(f"Import completed successfully!"))
                self.stdout.write(f"Imported: 1 attempt, {trace_count} traces, {image_count} images.")
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Import failed: {e}"))
