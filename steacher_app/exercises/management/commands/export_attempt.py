import os
import json
from django.core.management.base import BaseCommand, CommandError
from exercises.models import Attempt

class Command(BaseCommand):
    help = 'Exports a single attempt (by ID) with its traces and trace images to a JSON file.'

    def add_arguments(self, parser):
        parser.add_argument('attempt_id', type=int, help='ID of the attempt to export')

    def handle(self, *args, **options):
        attempt_id = options.get('attempt_id')
        if not attempt_id:
            raise CommandError('You must specify an attempt ID.')

        self.stdout.write(f"Exporting Attempt ID: {attempt_id}")
        try:
            attempt = Attempt.objects.get(pk=attempt_id)
        except Attempt.DoesNotExist:
            raise CommandError(f"Attempt with ID {attempt_id} does not exist.")

        # Build the export data
        attempt_data = {
            "exercise": getattr(attempt.exercise, 'id', None),
            "user": getattr(attempt.user, 'id', None),
            "cohort": getattr(attempt.cohort, 'id', None) if attempt.cohort else None,
            "complete": attempt.complete,
            "asked_for_solution": attempt.asked_for_solution,
            "version": attempt.version,
            "created_at": attempt.created_at.isoformat(),
            "updated_at": attempt.updated_at.isoformat(),
            "traces": []
        }

        traces = attempt.traces.all().order_by('rank_order', 'id')
        for trace in traces:
            trace_data = {
                "object": getattr(trace, 'object_id', None),
                "user": getattr(trace.user, 'id', None),
                "channel": trace.channel,
                "system_prompt": trace.system_prompt,
                "assistant_content": trace.assistant_content,
                "assistant_metadata": trace.assistant_metadata,
                "user_content": trace.user_content,
                "user_metadata": trace.user_metadata,
                "rank_order": trace.rank_order,
                "created_at": trace.created_at.isoformat(),
                "content_type": str(trace.content_type) if hasattr(trace, 'content_type') else "",
                "images": []
            }
            for image in trace.images.all().order_by('chain_position'):
                image_data = {
                    "image": str(image.image_bytes),
                    "upload_token": getattr(image, 'upload_token', ""),
                    "token_expires_at": image.token_expires_at.isoformat() if getattr(image, 'token_expires_at', None) else "",
                    "next_token": getattr(image, 'next_token', ""),
                    "image_type": image.image_type,
                    "file_size": image.file_size if image.file_size is not None else 0,
                    "chain_position": image.chain_position,
                    "uploaded_at": image.uploaded_at.isoformat() if image.uploaded_at else "",
                    "created_at": image.created_at.isoformat() if image.created_at else ""
                }
                trace_data["images"].append(image_data)
            attempt_data["traces"].append(trace_data)

        export_data = {"attempts": [attempt_data]}

        # Prepare output filename
        exports_dir = 'exports'
        if not os.path.exists(exports_dir):
            os.makedirs(exports_dir)
        base_filename = f"attempt_{attempt_id}.json"
        base_path = os.path.join(exports_dir, base_filename)
        final_path = base_path
        counter = 1
        while os.path.exists(final_path):
            final_path = os.path.join(exports_dir, f"attempt_{attempt_id}_{counter}.json")
            counter += 1

        # Write to file
        try:
            with open(final_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            self.stdout.write(self.style.SUCCESS(f"Export completed successfully!"))
            self.stdout.write(self.style.SUCCESS(f"File saved to: {final_path}"))
            self.stdout.write(f"Exported: Attempt {attempt_id} with {len(attempt_data['traces'])} traces.")
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to write file: {e}"))
