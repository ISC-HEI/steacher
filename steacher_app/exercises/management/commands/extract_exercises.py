import json
import fitz  # PyMuPDF
from PIL import Image
import io
import logging
from typing import List, Optional

from django.core.management.base import BaseCommand
from django.conf import settings
from google import genai
from google.genai.types import GenerateContentConfig, Part
from pydantic import BaseModel, Field

# Configuration
EXTRACT_MODEL = "gemini-3-pro-preview"  

logger = logging.getLogger(__name__)

class ExerciseRegion(BaseModel):
    exercise_id: str = Field(description="The exercise identifier/number, e.g. '1', '2a', '3'.")
    id_bbox: list[int] = Field(description="[y0, x0, y1, x1] bounding box for the exercise number/ID (normalized 0-1000).")
    question_bbox: list[int] = Field(description="[y0, x0, y1, x1] bounding box for the printed question text body (normalized 0-1000).")
    answer_bbox: list[int] = Field(description="[y0, x0, y1, x1] bounding box for the handwritten answer/annotation text body (normalized 0-1000). Returns [0,0,0,0] if no answer is found.")

class PageExtraction(BaseModel):
    exercises: List[ExerciseRegion] = Field(description="List of exercises found on the page.")

def treat_gemini_bbox(bbox: list[int], img_size: tuple[int, int]) -> list[int]:
    """
    Converts Gemini [y0, x0, y1, x1] normalized (0-1000) coordinates 
    to [x0, y0, x1, y1] pixel coordinates.
    """
    if not bbox or len(bbox) != 4:
        return []
        
    height, width = img_size
    y0, x0, y1, x1 = bbox
    
    # Normalize and scale
    x0_px = int(x0 / 1000 * width)
    y0_px = int(y0 / 1000 * height)
    x1_px = int(x1 / 1000 * width)
    y1_px = int(y1 / 1000 * height)
    
    return [x0_px, y0_px, x1_px, y1_px]

class Command(BaseCommand):
    help = 'Extract exercise bounding boxes from a PDF using Gemini Vision'

    def add_arguments(self, parser):
        parser.add_argument('pdf_path', type=str, help='Path to the PDF file')
        parser.add_argument('--pages', type=str, default="0-0", help='Page range (0-based, inclusive), e.g., "0-5". Default "0-0"')
        parser.add_argument('--output', type=str, default="exercises.json", help='Output JSON file path')

    def handle(self, *args, **options):
        pdf_path = options['pdf_path']
        page_range = options['pages']
        output_file = options['output']

        try:
            start_page, end_page = map(int, page_range.split('-'))
        except ValueError:
            self.stderr.write("Invalid page range format. Use 'start-end' (e.g., '0-5')")
            return

        if not settings.GEMINI_API_KEY:
            self.stderr.write("GEMINI_API_KEY not found in settings.")
            return

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        self.stdout.write(f"Opened PDF: {pdf_path} ({total_pages} pages)")

        results = []

        # Process pages
        for page_num in range(start_page, min(end_page + 1, total_pages)):
            self.stdout.write(f"Processing page {page_num}...")
            
            page = doc.load_page(page_num)
            pix = page.get_pixmap()
            img_data = pix.tobytes("png")
            
            # Keep track of dimensions for scaling later
            img_width = pix.width
            img_height = pix.height
            img_size = (img_height, img_width)

            prompt = """
            Analyze this image of a math worksheet. 
            Identify all distinct exercises. 
            
            Naming Rules:
            - If an exercise has sub-parts (e.g. 2 followed by a, b, c), treat each part as a distinct exercise (e.g. "2a", "2b", "2c").
            - Do NOT output the main number (e.g. "2") as a separate exercise if it splits into sub-parts.
            - Do NOT output sub-parts (e.g. "a", "b") without their parent number. Always combine them (e.g. "2a").
            
            For each exercise, extract three bounding boxes:
            1. 'id_bbox': The exercise number or identifier (e.g., "1", "2a", "Ex 3").
            2. 'question_bbox': The PRINTED text of the question. 
               - Ensure this covers the full width and height of the question text.
            3. 'answer_bbox': The HANDWRITTEN annotations or text that answer the question. 
               - CRITICAL: This box must encompass **ALL** handwritten work associated with the question.
               - Include ALL formulas, calculations, equations, graphs, diagrams, and side-notes.
               - The answer is often spread out horizontally or split into columns. Draw a SINGLE box that is large enough to contain EVERYTHING handwritten for that specific question.
               - If the handwriting starts on the left and goes to the right, the box must cover the full width.
               - If there are no handwritten marks for a question, set answer_bbox to [0,0,0,0].

            Return the coordinates as [ymin, xmin, ymax, xmax] on a scale of 0 to 1000.
            """

            try:
                response = client.models.generate_content(
                    model=EXTRACT_MODEL,
                    contents=[
                        Part(text=prompt),
                        Part.from_bytes(data=img_data, mime_type="image/png")
                    ],
                    config=GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=PageExtraction,
                        temperature=0.1,
                    )
                )

                if response.parsed:
                    page_extraction = response.parsed
                    # If it's a dict (sometimes happens despite typing), convert to model
                    if isinstance(page_extraction, dict):
                        page_extraction = PageExtraction(**page_extraction)
                    
                    for ex in page_extraction.exercises:
                        # Convert all bboxes to pixel coordinates
                        ex_data = {
                            "page": page_num,
                            "exercise_id": ex.exercise_id,
                            "id_bbox_norm": ex.id_bbox,
                            "question_bbox_norm": ex.question_bbox,
                            "answer_bbox_norm": ex.answer_bbox,
                            "id_bbox_px": treat_gemini_bbox(ex.id_bbox, img_size),
                            "question_bbox_px": treat_gemini_bbox(ex.question_bbox, img_size),
                            "answer_bbox_px": treat_gemini_bbox(ex.answer_bbox, img_size)
                        }
                        results.append(ex_data)
                        self.stdout.write(f"  Found Exercise {ex.exercise_id}")
                else:
                    self.stderr.write(f"  No structured response for page {page_num}")

            except Exception as e:
                self.stderr.write(f"  Error processing page {page_num}: {e}")

        # Save results
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)

        self.stdout.write(f"Extraction complete. Saved to {output_file}")
