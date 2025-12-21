import io
import tempfile
import json
import logging
import asyncio
import zipfile
from pathlib import Path
from typing import List, Tuple
from pydantic import BaseModel, Field
from django.db.models import Max
from asgiref.sync import sync_to_async
import google.genai.types as genai_types

from exercises.logic import gemini_client, _extract_thoughts_from_response, _build_authoring_system_prompt
from exercises.models import Module, Exercise, create_trace_for, Course
from .models import AuthoringSession

logger = logging.getLogger(__name__)


MODEL = "gemini-3-pro-preview"

# Text-based file extensions that should be sent as text/plain to Gemini
# Includes documents and programming language source files
TEXT_BASED_EXTENSIONS = {
    # Documents
    '.csv', '.json', '.tex', '.txt', '.md',
    # Python
    '.py',
    # Java/JVM
    '.java', '.kt', '.kts', '.scala', '.groovy',
    # JavaScript/TypeScript
    '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs',
    # C/C++
    '.c', '.cpp', '.cc', '.cxx', '.h', '.hpp', '.hxx',
    # C#
    '.cs', '.csx',
    # Go
    '.go',
    # Rust
    '.rs',
    # Ruby
    '.rb', '.rake',
    # PHP
    '.php',
    # Swift
    '.swift',
    # Kotlin
    '.kt', '.kts',
    # R
    '.r', '.R',
    # Shell
    '.sh', '.bash', '.zsh',
    # SQL
    '.sql',
    # HTML/CSS
    '.html', '.htm', '.css', '.scss', '.sass', '.less',
    # XML/YAML
    '.xml', '.yaml', '.yml',
    # Other
    '.m', '.matlab', '.pl', '.lua', '.vim',
}

# All accepted file formats for upload (text-based + binary formats)
ACCEPTED_UPLOAD_EXTENSIONS = TEXT_BASED_EXTENSIONS | {'.pdf', '.zip'}
# For HTML accept attribute
ACCEPTED_UPLOAD_FORMATS = ','.join(sorted(ACCEPTED_UPLOAD_EXTENSIONS)) + ',image/*'


import sys

# Ensure logger outputs to console for background thread visibility
# We force a handler to stdout to ensure visibility in Docker/Django logs
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('[AI_LOGIC] %(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(console_handler)
logger.setLevel(logging.INFO)




class SegmentedExercise(BaseModel):
    """Single exercise extracted from documents"""
    title: str = Field(description="Exercise title/name")
    content: str = Field(description="Full problem statement that students will see")
    solution: str = Field(description="Expected solution/answer. Empty string if not provided in document")


class SegmentationResult(BaseModel):
    """Result of Phase 1: document segmentation"""
    module_name: str = Field(description="Suggested module name based on document content")
    module_description: str = Field(description="Brief module description")
    message_to_teacher: str = Field(description="High-level observations about document quality, extraction notes, or issues. Do NOT list exercise details or counts.")
    errors_to_teacher: str = Field(description="String describing critical errors encountered during extraction (e.g. mismatched solutions, missing images). Empty string if none.", default="")
    exercises: List[SegmentedExercise] = Field(description="List of segmented exercises in document order")


def create_file_parts(session, max_files=20):
    """
    Create Gemini Part objects from session files for inline data.
    Extracts ZIP files and processes their contents.
    Returns list of Part objects that can be included in messages.
    
    Args:
        session: AuthoringSession instance
        max_files: Maximum number of files to process (default 20)
    """
    file_parts = []
    
    for file in session.files.all():
        try:
            file_ext = Path(file.filename).suffix.lower()
            
            # Convert memoryview to bytes if needed
            file_data = file.file_data
            if isinstance(file_data, memoryview):
                file_data = bytes(file_data)
            
            # Handle ZIP files - extract and process contents
            if file_ext == '.zip':
                try:
                    with zipfile.ZipFile(io.BytesIO(file_data)) as zf:
                        for zip_info in zf.infolist():
                            # Check file limit
                            if len(file_parts) >= max_files:
                                print(f"Reached maximum file limit ({max_files}), stopping extraction")
                                break
                            
                            # Skip directories
                            if zip_info.is_dir():
                                continue
                            
                            # Skip hidden files (any path component starting with .)
                            path_parts = Path(zip_info.filename).parts
                            if any(part.startswith('.') for part in path_parts):
                                continue
                            
                            # Extract file
                            extracted_data = zf.read(zip_info.filename)
                            extracted_ext = Path(zip_info.filename).suffix.lower()
                            
                            # Determine MIME type for extracted file
                            if extracted_ext in TEXT_BASED_EXTENSIONS:
                                extracted_mime = 'text/plain'
                            elif extracted_ext == '.pdf':
                                extracted_mime = 'application/pdf'
                            elif extracted_ext in {'.png', '.jpg', '.jpeg'}:
                                extracted_mime = f'image/{extracted_ext[1:]}'
                            elif extracted_ext == '.webp':
                                extracted_mime = 'image/webp'
                            else:
                                # Skip unsupported file types
                                print(f"Skipping unsupported file in ZIP: {zip_info.filename}")
                                continue
                            
                            # Create part for extracted file
                            file_part = genai_types.Part.from_bytes(
                                data=extracted_data,
                                mime_type=extracted_mime
                            )
                            file_parts.append(file_part)
                            print(f"Extracted from ZIP: {zip_info.filename} ({extracted_mime})")
                            
                except zipfile.BadZipFile:
                    print(f"Error: {file.filename} is not a valid ZIP file")
                    continue
            else:
                # Check file limit
                if len(file_parts) >= max_files:
                    print(f"Reached maximum file limit ({max_files}), skipping remaining files")
                    break
                
                # Regular file (not ZIP)
                # Determine MIME type
                if file_ext in TEXT_BASED_EXTENSIONS:
                    mime_type = 'text/plain'
                else:
                    mime_type = file.content_type or 'application/pdf'
                
                file_part = genai_types.Part.from_bytes(
                    data=file_data,
                    mime_type=mime_type
                )
                file_parts.append(file_part)
            
        except Exception as e:
            # If creation fails, skip this file and continue
            print(f"Error creating part for {file.filename}: {str(e)}")
            continue
    
    return file_parts


def call_gemini_for_import(session) -> Tuple[SegmentationResult, list[str]]:
    """
    Call Gemini 3 Pro to analyze documents and extract exercises with structured output.
    Returns tuple of (SegmentationResult, thoughts).
    """
    teacher_lang = session.created_by.preferred_language or 'en'
    
    # Load prompt template
    prompt_path = Path(__file__).parent / 'content_import_prompt.md'
    with open(prompt_path, 'r') as f:
        system_prompt = f.read().replace('{language}', teacher_lang)
    
    # Create file parts and send to Gemini
    file_parts = create_file_parts(session)
    
    # Include course-specific context if available
    course_context = ""
    if session.course.course_prompt:
        course_context = f"""

# Course Context

{session.course.course_prompt}
"""
    
    initial_text = f"""{system_prompt}{course_context}

Teacher instructions: {session.teacher_instructions or 'None'}

Please analyze these documents, segment the exercises, and extract their content."""
    
    # Build parts: text + file parts
    parts = [genai_types.Part(text=initial_text)] + file_parts
    
    contents = [{
        'role': 'user',
        'parts': parts
    }]
    
    # Call Gemini 3 Pro with structured output
    response = gemini_client.models.generate_content(
        model=MODEL,
        contents=contents,
        config={
            'response_mime_type': 'application/json',
            'response_json_schema': SegmentationResult.model_json_schema(),
            'thinking_config': genai_types.ThinkingConfig(include_thoughts=True)
        }
    )
    
    # Extract thoughts from response (if any)
    thoughts = _extract_thoughts_from_response(response)
    
    # Parse structured result
    result = SegmentationResult.model_validate_json(response.text)
    return result, thoughts


async def generate_authoring_update_async(exercise_payload: dict, user_message: str, course: Course, mode: str = 'edit') -> dict:
    """
    Async version of generate_authoring_update for parallel exercise building.
    Uses Google Gemini async client (client.aio.models.generate_content).
    
    Input:
    - exercise_payload: current exercise DTO as dict
    - user_message: single user message (not full conversation history)
    - course: Course instance
    - mode: 'edit' (modify exercise) or 'feedback' (provide feedback)
    
    Output:
    - assistant_message: str
    - updated_exercise: dict (complete exercise DTO)
    """
    from exercises.schemas import AuthoringAssistantResponse
    
    # Build system prompt using shared helper
    system_prompt = _build_authoring_system_prompt(exercise_payload, course, mode)
    
    # Build messages for Gemini (simple 3-turn conversation)
    contents = [
        {'role': 'user', 'parts': [genai_types.Part(text=system_prompt)]},
        {'role': 'model', 'parts': [genai_types.Part(text="I understand. I'm ready to help you with this exercise.")]},
        {'role': 'user', 'parts': [genai_types.Part(text=user_message)]}
    ]
    
    # Call Gemini async
    try:
        config = {'temperature': 0.2}
        if mode == 'edit':
            config['response_mime_type'] = 'application/json'
            config['response_json_schema'] = AuthoringAssistantResponse.model_json_schema()
        
        response = await gemini_client.aio.models.generate_content(
            model=MODEL,
            contents=contents,
            config=config
        )
        
        # Parse with Pydantic for strict validation
        if mode == 'edit':
            authoring_response = AuthoringAssistantResponse.model_validate_json(response.text)
            return {
                'assistant_message': authoring_response.assistant_message,
                'updated_exercise': authoring_response.updated_exercise.model_dump(),
            }
        else:
            # Feedback mode
            return {
                'assistant_message': (response.text or '').strip(),
                'updated_exercise': exercise_payload,
            }
            
    except Exception as e:
        logger.error(f"Failed to create completion for authoring assistant: {e}")
        return {
            'assistant_message': f"Error contacting AI assistant: {e}",
            'updated_exercise': exercise_payload,
        }


async def build_single_exercise_async(session, module, idx, ex_data):
    """
    Build a single exercise using the async authoring assistant.
    Called in parallel via asyncio.gather().
    """
    try:
        logger.info(f"[Phase II Async] build_single_exercise: idx={idx}, title='{ex_data.get('title', 'Untitled')}'")
        
        # Create minimal draft exercise (sync DB operation)
        @sync_to_async
        def create_exercise(mod_id):
            # We fetch module by ID to ensure we are in the correct thread context
            mod = Module.objects.get(id=mod_id)
            return Exercise.objects.create(
                module=mod,
                order=idx,
                title_i18n={'en': ex_data['title']},
                question_i18n={'en': ex_data['content']},
                description_i18n={'en': ''},
                exercise_type='open_question',
                exercise_data={},
                answer_data={},
                visible=False,
                # Set a marker that we can check in the UI
                draft_notes="Generating content..." 
            )
        
        exercise = await create_exercise(module.id)
        # Force print to stdout to ensure visibility in dev console
        print(f"--- [Async Thread] Created minimal exercise {exercise.id}: {ex_data.get('title')} ---")
        logger.info(f"[Phase II Async] Exercise created: id={exercise.id}")
        
        # Build exercise payload for authoring assistant
        exercise_payload = {
            'id': exercise.id,
            'title_i18n': exercise.title_i18n,
            'description_i18n': exercise.description_i18n,
            'question_i18n': exercise.question_i18n,
            'exercise_type': exercise.exercise_type,
            'exercise_data': exercise.exercise_data,
            'answer_data': exercise.answer_data,
        }
        
        # Build prompt
        solution_context = f"\n\nExpected solution:\n{ex_data['solution']}" if ex_data.get('solution') else ""
        authoring_prompt = f"""Create a proper exercise from this content. Detect the exercise type, generate appropriate tests/hints, and format it correctly.

Problem statement:
{ex_data['content']}{solution_context}"""
        
        logger.info(f"[Phase II Async] Calling async authoring assistant for exercise {exercise.id}")
        
        # Call async authoring assistant (timeout handled at Gemini level)
        print(f"--- [Async Thread] Calling Gemini for exercise {exercise.id}... ---")
        result = await generate_authoring_update_async(
            exercise_payload=exercise_payload,
            user_message=authoring_prompt,
            course=session.course,
            mode='edit'
        )
        print(f"--- [Async Thread] Gemini returned for exercise {exercise.id} ---")
        logger.info(f"[Phase II Async] Authoring assistant returned for exercise {exercise.id}: {result.keys() if result else 'None'}")
        
        # Update exercise with result
        @sync_to_async
        def update_exercise():
            # Refresh from DB
            ex = Exercise.objects.get(id=exercise.id)
            
            if result and 'updated_exercise' in result:
                updates = result['updated_exercise']
                logger.info(f"[Phase II Async] Applying updates to exercise {exercise.id}. Keys to update: {list(updates.keys())}")
                
                # Fields that should NEVER be updated by the AI
                protected_fields = {'id', 'pk', 'order', 'module', 'module_id', 'course', 'course_id'}
                
                for key, value in updates.items():
                    if key in protected_fields:
                        continue
                    if hasattr(ex, key):
                        # logger.info(f"Updating {key} for exercise {exercise.id} with value length {len(str(value))}")
                        setattr(ex, key, value)
                
                if 'assistant_message' in result:
                    ex.draft_notes = result['assistant_message']
                    logger.info(f"[Phase II Async] Draft notes set for exercise {exercise.id}: {ex.draft_notes[:50]}...")
                
                ex.save()
                logger.info(f"[Phase II Async] Exercise {exercise.id} saved successfully")
            else:
                logger.warning(f"[Phase II Async] No updated_exercise in result for exercise {exercise.id}")
        
        await update_exercise()
    
    except Exception as e:
        logger.error(f"[Phase II Async] Authoring assistant failed for exercise: {str(e)}", exc_info=True)
        # We can't save the error note if exercise creation failed, 
        # but if exercise exists we should try to save it
        if 'exercise' in locals():
             try:
                @sync_to_async
                def save_error():
                    ex = Exercise.objects.get(id=exercise.id)
                    ex.draft_notes = f"Error during automatic building: {str(e)}\n\nPlease review and complete this exercise manually."
                    ex.save()
                await save_error()
             except Exception:
                 pass


async def build_all_exercises_async(session_id: int):
    """
    Background coroutine that builds all exercises in parallel.
    This runs in the background after the view returns.
    """
    logger.info(f"[Phase II Async] Starting build_all_exercises for session {session_id}")
    
    # Get session (sync DB operation)
    @sync_to_async
    def get_session():
        # Pre-fetch course to avoid lazy loading issues in async context
        return AuthoringSession.objects.select_related('course').get(id=session_id)
    
    session = await get_session()
    segmentation = session.segmentation_data
    
    if not segmentation or not segmentation.get('exercises'):
        logger.error(f"[Phase II Async] No segmentation data for session {session_id}")
        return
    
    exercise_count = len(segmentation.get('exercises', []))
    logger.info(f"[Phase II Async] Session {session_id}: found {exercise_count} exercises to build")
    
    # Update status to building
    @sync_to_async
    def set_building():
        s = AuthoringSession.objects.get(id=session_id)
        s.status = 'building'
        s.save()
    
    await set_building()
    logger.info(f"[Phase II Async] Status set to 'building'")
    
    # Create module
    @sync_to_async
    def create_module():
        s = AuthoringSession.objects.get(id=session_id)
        last_order = s.course.modules.aggregate(Max('order'))['order__max'] or -1
        module = Module.objects.create(
            course=s.course,
            name=segmentation['module_name'],
            description=segmentation['module_description'],
            order=last_order + 1
        )
        s.module = module
        s.save(update_fields=['module'])
        return module
    
    module = await create_module()
    logger.info(f"[Phase II Async] Module created: id={module.id}, name='{module.name}'")
    
    # Build all exercises in parallel
    exercises_data = segmentation['exercises']
    tasks = [
        build_single_exercise_async(session, module, idx, ex_data)
        for idx, ex_data in enumerate(exercises_data)
    ]
    
    logger.info(f"[Phase II Async] Starting parallel build of {len(tasks)} exercises")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    logger.info(f"[Phase II Async] Parallel build complete. Results: {len([r for r in results if not isinstance(r, Exception)])} succeeded, {len([r for r in results if isinstance(r, Exception)])} failed")
    
    # Update status to active
    @sync_to_async
    def set_active():
        s = AuthoringSession.objects.get(id=session_id)
        s.status = 'active'
        s.save()
    
    await set_active()
    logger.info(f"[Phase II Async] Session {session_id} completed successfully")


def run_full_import_pipeline(session_id: int):
    """
    Orchestrates the full import pipeline in a background thread:
    1. Phase 1: Document analysis & segmentation (Sync)
    2. Phase 2: Exercise generation (Async)
    
    This function is designed to be the target of a threading.Thread.
    """
    print(f"DEBUG: run_full_import_pipeline started for session {session_id}", flush=True)
    logger.info(f"[Full Pipeline] Starting for session {session_id}")
    
    try:
        # 1. Get Session
        try:
            print(f"DEBUG: Fetching session {session_id}", flush=True)
            session = AuthoringSession.objects.get(id=session_id)
        except AuthoringSession.DoesNotExist:
            print(f"DEBUG: Session {session_id} not found", flush=True)
            logger.error(f"[Full Pipeline] Session {session_id} not found")
            return

        # 2. Phase 1: Analysis (Sync)
        print(f"DEBUG: Starting Phase 1 (Analysis) for session {session_id}", flush=True)
        logger.info(f"[Full Pipeline] Phase 1: Calling Gemini for segmentation...")
        try:
            segmentation_result, thoughts = call_gemini_for_import(session)
            
            # Store segmentation
            session.segmentation_data = segmentation_result.model_dump()
            
            # Create trace for history (optional but good for debugging)
            create_trace_for(
                owner_obj=session,
                user=session.created_by,
                channel='content_import',
                assistant_content={'message_to_teacher': segmentation_result.message_to_teacher},
                assistant_metadata={'segmentation': session.segmentation_data}
            )
            
            session.save()
            print(f"DEBUG: Phase 1 complete. Found {len(segmentation_result.exercises)} exercises.", flush=True)
            logger.info(f"[Full Pipeline] Phase 1 complete. Found {len(segmentation_result.exercises)} exercises.")
            
        except TimeoutError:
            print(f"DEBUG: Phase 1 timed out after 60 seconds", flush=True)
            logger.error(f"[Full Pipeline] Phase 1 timed out after 60 seconds")
            session.status = 'timeout'
            session.error_message = "Phase I (document analysis) timed out after 60 seconds"
            session.save()
            return
        except Exception as e:
            print(f"DEBUG: Phase 1 failed: {e}", flush=True)
            logger.error(f"[Full Pipeline] Phase 1 failed: {e}", exc_info=True)
            session.status = 'error'
            session.error_message = f"Phase I failed: {str(e)}"
            session.save()
            return

        # 3. Phase 2: Generation (Async)
        print(f"DEBUG: Starting Phase 2 (Generation) for session {session_id}", flush=True)
        logger.info(f"[Full Pipeline] Phase 2: Starting async exercise generation...")
        
        # Run the async build process
        asyncio.run(build_all_exercises_async(session_id))
        
        print(f"DEBUG: All phases completed for session {session_id}", flush=True)
        logger.info(f"[Full Pipeline] All phases completed for session {session_id}")
        
    except Exception as e:
        print(f"DEBUG: Critical error in pipeline: {e}", flush=True)
        logger.error(f"[Full Pipeline] Critical error: {e}", exc_info=True)
        try:
            session = AuthoringSession.objects.get(id=session_id)
            session.status = 'error'
            session.error_message = f"Critical error: {str(e)}"
            session.save()
        except Exception:
            pass
