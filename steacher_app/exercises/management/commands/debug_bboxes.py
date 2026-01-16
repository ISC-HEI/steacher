import json
import fitz  # PyMuPDF
import logging
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Draw bounding boxes from exercises.json onto the PDF for debugging'

    def add_arguments(self, parser):
        parser.add_argument('pdf_path', type=str, help='Path to the original PDF file')
        parser.add_argument('--json', type=str, default="exercises.json", help='Path to the exercises JSON file')
        parser.add_argument('--output', type=str, default="debug_output.pdf", help='Output annotated PDF file path')

    def handle(self, *args, **options):
        pdf_path = options['pdf_path']
        json_path = options['json']
        output_path = options['output']

        # Load exercises
        try:
            with open(json_path, 'r') as f:
                exercises = json.load(f)
        except FileNotFoundError:
            self.stderr.write(f"JSON file not found: {json_path}")
            return

        # Open PDF
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            self.stderr.write(f"Could not open PDF: {e}")
            return

        self.stdout.write(f"Loaded {len(exercises)} exercises. Annotating PDF...")

        # Process each exercise
        for ex in exercises:
            page_num = ex.get('page')
            if page_num is None or page_num >= len(doc):
                continue
            
            page = doc[page_num]
            w = page.rect.width
            h = page.rect.height

            # Helper to convert [y0, x0, y1, x1] normalized to [x0, y0, x1, y1] points
            def norm_to_rect(bbox_norm):
                if not bbox_norm or len(bbox_norm) != 4:
                    return None
                y0, x0, y1, x1 = bbox_norm
                
                # Check for empty bbox (all zeros)
                if all(v == 0 for v in bbox_norm):
                    return None

                return fitz.Rect(
                    (x0 / 1000) * w,
                    (y0 / 1000) * h,
                    (x1 / 1000) * w,
                    (y1 / 1000) * h
                )

            # Draw ID Box (Red)
            id_rect = norm_to_rect(ex.get('id_bbox_norm'))
            if id_rect:
                page.draw_rect(id_rect, color=(1, 0, 0), width=1.5)
                # Add label
                page.insert_text(
                    (id_rect.x0, id_rect.y0 - 5), 
                    f"ID: {ex.get('exercise_id')}", 
                    color=(1, 0, 0), 
                    fontsize=8
                )

            # Draw Question Box (Blue)
            q_rect = norm_to_rect(ex.get('question_bbox_norm'))
            if q_rect:
                page.draw_rect(q_rect, color=(0, 0, 1), width=1.0)
                page.insert_text(
                    (q_rect.x0, q_rect.y0 - 2), 
                    "Question", 
                    color=(0, 0, 1), 
                    fontsize=6
                )

            # Draw Answer Box (Green)
            a_rect = norm_to_rect(ex.get('answer_bbox_norm'))
            if a_rect:
                page.draw_rect(a_rect, color=(0, 1, 0), width=1.0)
                page.insert_text(
                    (a_rect.x0, a_rect.y0 - 2), 
                    "Answer", 
                    color=(0, 1, 0), 
                    fontsize=6
                )

        # Save output
        doc.save(output_path)
        self.stdout.write(f"Saved annotated PDF to {output_path}")
