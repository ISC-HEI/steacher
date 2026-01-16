import json
import fitz  # PyMuPDF
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from google import genai
from google.genai.types import GenerateContentConfig, Part
from exercises.models import Course, Module, Exercise
from exercises.logic import generate_authoring_update, MODEL_PRO

logger = logging.getLogger(__name__)

TRANSCRIPTION_PROMPT = """
You are an expert math transcriber and reviewer. 
Your task is to transcribe the math question and the handwritten answer from the provided images into LaTeX/Text, AND to identify any potential mathematical errors in the solution.

Image 1: The Question (printed text). 
- Transcribe the question text exactly as it appears.
- Use LaTeX for all mathematical expressions (e.g. $x^2$, $\\frac{1}{2}$).
- If the image cuts off part of the question but the context makes it obvious, infer the missing characters.
- Note: This image includes a margin around the detected question. Ignore text from adjacent exercises. Focus on the main question block in the center.

Image 2: The Answer (handwritten).
- Transcribe the handwritten solution exactly as written, including any "scratch work" or mistakes.
- Use LaTeX for math.
- Captures all steps and formulas. Briefly describe diagrams in text if they are key to the solution.

Critique & Validation:
- As you transcribe, check the mathematical logic and calculations.
- Identify any typos, arithmetical errors, or logical inconsistencies in the handwritten work compared to the question.

Output Format (JSON):
{
  "question_text": "The transcribed question...",
  "answer_text": "The transcribed answer (exact transcription)...",
  "detected_errors": "List any math errors, typos, or inconsistencies found in the handwritten work, or 'None'."
}

IMPORTANT: You are outputting raw JSON. 
- All LaTeX backslashes MUST be double-escaped (e.g. output "\\\\frac" instead of "\\frac"). This is CRITICAL for valid JSON.
- Do not output markdown code fences (like ```json).
"""

class Command(BaseCommand):
    help = 'Create exercises from extracted bounding boxes and PDF'

    def add_arguments(self, parser):
        parser.add_argument('--course_id', type=int, default=21, help='Target Course ID (default: 21)')
        parser.add_argument('--module_name', type=str, default="Examen semestriel Algèbre Linéaire 2024", help='Name of the module to create')
        parser.add_argument('--json_file', type=str, default="steacher_app/exercises.json", help='Path to exercises.json')
        parser.add_argument('--pdf_file', type=str, default="project_subparts/math/data/semestriels_annoté.pdf", help='Path to PDF file')
        parser.add_argument('--margin_px', type=int, default=100, help='Margin in pixels to add around question bbox')

    def handle(self, *args, **options):
        course_id = options['course_id']
        module_name = options['module_name']
        json_path = options['json_file']
        pdf_path = options['pdf_file']
        margin = options['margin_px']

        # 1. Setup Course and Module
        try:
            course = Course.objects.get(pk=course_id)
            self.stdout.write(f"Found Course: {course.name} (ID: {course.id})")
        except Course.DoesNotExist:
            self.stderr.write(f"Course with ID {course_id} not found.")
            return

        # Create new module (idempotent-ish: create if not exists, but user asked for "new module")
        # To ensure "new", we can check if it exists and append a number or just get_or_create.
        # User said "create a new module", implies a distinct one.
        # But if we run this script multiple times, we probably want to update the same one or delete old.
        # For safety, I'll use get_or_create to avoid duplicates on re-runs.
        module, created = Module.objects.get_or_create(
            course=course, 
            name=module_name,
            defaults={'visible': False} # Start hidden
        )
        if created:
            self.stdout.write(f"Created new Module: {module.name}")
        else:
            self.stdout.write(f"Using existing Module: {module.name}")

        # 2. Load JSON
        try:
            with open(json_path, 'r') as f:
                exercises_metadata = json.load(f)
            self.stdout.write(f"Loaded {len(exercises_metadata)} exercises from {json_path}")
        except FileNotFoundError:
            self.stderr.write(f"JSON file not found: {json_path}")
            return

        # 3. Open PDF
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            self.stderr.write(f"Failed to open PDF {pdf_path}: {e}")
            return

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        # 4. Process Loop
        for i, item in enumerate(exercises_metadata):
            ex_id = item.get('exercise_id', f"Unknown-{i}")
            
            #if str(ex_id) not in ['8a', '8b']:
            #    continue

            self.stdout.write(f"\n--- Processing Exercise {ex_id} ---")

            # Check if exercise already exists in this module to avoid duplication?

            page_num = item['page']
            q_bbox = item['question_bbox_px'] # [x0, y0, x1, y1]
            a_bbox = item['answer_bbox_px']   # [x0, y0, x1, y1]

            if not q_bbox or len(q_bbox) != 4:
                self.stderr.write(f"Invalid question bbox for {ex_id}. Skipping.")
                continue

            # Load Page
            page = doc.load_page(page_num)
            
            # --- Prepare Question Image ---
            # Add margin
            rect = page.rect # width, height
            x0, y0, x1, y1 = q_bbox
            
            # Expand
            x0 = max(0, x0 - margin)
            y0 = max(0, y0 - margin)
            x1 = min(rect.width, x1 + margin)
            y1 = min(rect.height, y1 + margin)
            
            q_rect = fitz.Rect(x0, y0, x1, y1)
            q_pix = page.get_pixmap(clip=q_rect)
            q_png = q_pix.tobytes("png")

            # --- Prepare Answer Image ---
            # If a_bbox is [0,0,0,0], we might have no answer
            has_answer = False
            a_png = None
            if a_bbox and any(v != 0 for v in a_bbox):
                has_answer = True
                ax0, ay0, ax1, ay1 = a_bbox
                a_rect = fitz.Rect(ax0, ay0, ax1, ay1)
                a_pix = page.get_pixmap(clip=a_rect)
                a_png = a_pix.tobytes("png")
            
            # --- Transcribe with Gemini ---
            self.stdout.write("  Transcribing images...")
            
            # Incorporate course prompt for notation/context if available
            transcription_prompt = TRANSCRIPTION_PROMPT
            if course.course_prompt:
                transcription_prompt += f"""
**Additional Course Context:**
These instructions were provided by the teacher for this specific course. They may include:
- information about the course contents, objectives, target audience, etc.
- a summary of the course content itself. In this case, use it to refer to parts of the course content itself in your answers
- notations to use and concepts to avoid

(start of course-specific instructions)
{course.course_prompt}
(end of course-specific instructions)

"""

            prompt_parts = [Part(text=transcription_prompt)]
            prompt_parts.append(Part.from_bytes(data=q_png, mime_type="image/png"))
            if has_answer:
                prompt_parts.append(Part(text="Image 2 (Answer):"))
                prompt_parts.append(Part.from_bytes(data=a_png, mime_type="image/png"))
            else:
                prompt_parts.append(Part(text="No handwritten answer provided for this exercise."))

            try:
                transcription_resp = client.models.generate_content(
                    model=MODEL_PRO,
                    contents=[prompt_parts],
                    config=GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1,
                        thinking_config=genai.types.ThinkingConfig(include_thoughts=True)
                    )
                )

                if not transcription_resp.candidates:
                    self.stderr.write(f"  Transcription failed: No candidates returned. (Response: {transcription_resp})")
                    continue

                # Extract and print thoughts
                for candidate in transcription_resp.candidates:
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                        for part in candidate.content.parts:
                            if hasattr(part, 'thought') and part.thought:
                                self.stdout.write(self.style.WARNING(f"\n--- THOUGHTS for Exercise {ex_id} ---\n{part.text}\n----------------------------------\n"))

                # Try to use the parsed response first
                if transcription_resp.parsed:
                     # SDK automatically handles JSON parsing when response_mime_type is application/json
                     # However, sometimes it returns a Pydantic model or similar object if response_schema was set (which it isn't here)
                     # Or a simple dict/list if no schema was set.
                     try:
                         if isinstance(transcription_resp.parsed, dict):
                             transcription = transcription_resp.parsed
                         else:
                             # Fallback to text parsing if parsed isn't a dict (shouldn't happen with simple JSON response)
                             transcription = json.loads(transcription_resp.text)
                     except Exception:
                         transcription = json.loads(transcription_resp.text)
                else:
                    # Fallback to manual parsing
                    try:
                        transcription = json.loads(transcription_resp.text)
                    except json.JSONDecodeError:
                        # Attempt to fix single backslashes in LaTeX
                        raw_text = transcription_resp.text or "{}"
                        fixed_text = raw_text.replace('\\', '\\\\').replace('\\\\\\\\', '\\\\')
                        try:
                            transcription = json.loads(fixed_text)
                        except json.JSONDecodeError:
                            self.stderr.write("  JSON parsing failed. Skipping.")
                            continue

                q_text = transcription.get('question_text', '')
                a_text = transcription.get('answer_text', '')
                detected_errors = transcription.get('detected_errors', 'None')
                
                # Handle case where detected_errors might be a list or string
                if isinstance(detected_errors, list):
                    detected_errors = ", ".join(map(str, detected_errors))
                else:
                    detected_errors = str(detected_errors)

                if detected_errors.lower() != 'none' and detected_errors.strip():
                    self.stdout.write(self.style.WARNING(f"  DETECTED ERRORS: {detected_errors}"))
                
            except Exception as e:
                self.stderr.write(f"  Transcription failed: {e}")
                continue

            # --- Generate Exercise with Authoring Assistant ---
            self.stdout.write("  Generating exercise content...")
            
            # Initial payload
            exercise_payload = {
                "exercise_type": "open_question", # Default as requested
                "title_i18n": {"en": f"Exercise {ex_id}", "fr": f"Exercice {ex_id}", "de": f"Übung {ex_id}"},
                "question_i18n": {"en": "", "fr": "", "de": ""},
                "description_i18n": {},
                "exercise_data": {"answer_template": ""},
                "answer_data": {"correct_answers": [], "hints": ""},
                "allow_image_upload": True
            }

            user_msg = f"""
I want to create a new Open Question exercise based on this math problem.

**Source Question (transcribed from printed text):**
{q_text}

**Handwritten Answer (transcribed from image):**
{a_text}

**Errors Detected by Transcriber (if any):**
{detected_errors}

Please:
1. Create a clear, well-formatted question in Markdown/LaTeX.
2. Translate it into English, French, and German.
3. Use the handwritten answer to populate the 'correct_answers' and 'explanation' fields. 
   - The 'answer' field in correct_answers should contain the final result/solution.
   - The 'explanation' field should contain the steps derived from the handwritten work.
   - IMPORTANT: If errors were detected in the handwritten work, DO NOT fix them in the transcription, but DO address them in the 'explanation' or add a note to the teacher in the 'assistant_message' field.
4. Set 'allow_image_upload' to true.
"""

            # Call logic
            result = generate_authoring_update(
                exercise_payload=exercise_payload,
                messages=[{'role': 'user', 'content': user_msg}],
                course=course,
                mode='edit'
            )
            
            updated_ex_data = result.get('updated_exercise')
            if not updated_ex_data:
                self.stderr.write(f"  Failed to generate exercise data: {result.get('assistant_message')}")
                continue

            llm_response = result.get('assistant_message')
            self.stdout.write(f"  LLM Response: {llm_response}")

            # --- Save to DB ---
            self.stdout.write("  Saving to database...")
            
            # Create instance
            # Determine order: get max order for this module + 1, or use loop index if we can be sure
            from django.db.models import Max
            max_order = Exercise.objects.filter(module=module).aggregate(Max('order'))['order__max']
            new_order = (max_order + 1) if max_order is not None else 0

            new_exercise = Exercise(
                module=module,
                exercise_type=updated_ex_data.get('exercise_type', 'open_question'),
                title_i18n=updated_ex_data.get('title_i18n', {}),
                description_i18n=updated_ex_data.get('description_i18n', {}),
                question_i18n=updated_ex_data.get('question_i18n', {}),
                exercise_data=updated_ex_data.get('exercise_data', {}),
                answer_data=updated_ex_data.get('answer_data', {}),
                allow_image_upload=updated_ex_data.get('allow_image_upload', True),
                order=new_order
            )
            new_exercise.save()
            self.stdout.write(f"  SUCCESS: Created Exercise {new_exercise.id} ({new_exercise.title})")

        self.stdout.write("\nAll Done!")
