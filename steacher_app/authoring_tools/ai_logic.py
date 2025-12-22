import io
import logging
import asyncio
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field
from django.db.models import Max
from asgiref.sync import sync_to_async
import google.genai.types as genai_types

from exercises.logic import gemini_client, _build_authoring_system_prompt
from exercises.models import Module, Exercise, Course
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


# ============================================================================
# Question Generator: Gemini File API and Context Cache Helpers
# ============================================================================

def upload_file_to_gemini(file_data: bytes, filename: str, mime_type: str) -> str:
    """
    Upload a file to Gemini File API and return the file URI.
    Files are stored for 48 hours.
    
    Args:
        file_data: Binary file content
        filename: Original filename
        mime_type: MIME type (e.g., 'application/pdf', 'text/plain')
    
    Returns:
        File URI (e.g., 'files/abc123')
    """
    try:
        # Convert memoryview to bytes if needed
        if isinstance(file_data, memoryview):
            file_data = bytes(file_data)
        
        # Determine MIME type for Gemini
        file_ext = Path(filename).suffix.lower()
        if file_ext in TEXT_BASED_EXTENSIONS:
            gemini_mime_type = 'text/plain'
        else:
            gemini_mime_type = mime_type
        
        # Upload to Gemini File API
        uploaded_file = gemini_client.files.upload(
            file=io.BytesIO(file_data),
            config={'mime_type': gemini_mime_type, 'display_name': filename}
        )
        
        logger.info(f"Uploaded file to Gemini: {filename} -> {uploaded_file.uri}")
        return uploaded_file.uri
        
    except Exception as e:
        logger.error(f"Failed to upload file to Gemini: {filename}, error: {e}")
        raise


def create_or_update_cache(session, system_prompt: str, course_context: str) -> str:
    """
    Create or update Gemini context cache for a session.
    Cache includes: system prompt + course context + file URIs.
    
    Args:
        session: AuthoringSession instance
        system_prompt: System prompt text
        course_context: Course context text
    
    Returns:
        Cache name (e.g., 'cachedContents/abc123')
    """
    try:
        # Build cache contents - start with combined text
        combined_text = f"{system_prompt}\n\n{course_context}"
        
        cache_parts = [genai_types.Part(text=combined_text)]
        
        # Add file URIs from session
        for uploaded_file in session.files.all():
            if uploaded_file.gemini_file_uri:
                # Determine MIME type
                file_ext = Path(uploaded_file.filename).suffix.lower()
                if file_ext in TEXT_BASED_EXTENSIONS:
                    mime_type = 'text/plain'
                else:
                    mime_type = uploaded_file.content_type
                
                # Create file part from URI
                file_part = genai_types.Part.from_uri(
                    file_uri=uploaded_file.gemini_file_uri,
                    mime_type=mime_type
                )
                cache_parts.append(file_part)
        
        # Delete old cache if exists
        if session.cache_name:
            try:
                gemini_client.caches.delete(name=session.cache_name)
                logger.info(f"Deleted old cache: {session.cache_name}")
            except Exception as e:
                logger.warning(f"Failed to delete old cache: {e}")
        
        # Create new cache
        cache = gemini_client.caches.create(
            model=MODEL,
            config=genai_types.CreateCachedContentConfig(
                display_name=f"Session {session.id} - {session.course.name}",
                contents=[{'role': 'user', 'parts': cache_parts}],
                ttl='3600s'  # 1 hour
            )
        )
        
        logger.info(f"Created cache: {cache.name} with {len(cache_parts)} parts")
        return cache.name
        
    except Exception as e:
        logger.error(f"Failed to create cache: {e}")
        raise


def build_course_context_for_generator(course: Course) -> str:
    """
    Build course context string for question generator chat prompt.
    Includes: course description, course_prompt, existing exercises.
    
    Args:
        course: Course instance
    
    Returns:
        Formatted course context string
    """
    context_parts = []
    
    # Course description
    if course.description:
        context_parts.append(f"**Course Description:**\n{course.description}\n")
    
    # Course prompt (if available)
    if course.course_prompt:
        context_parts.append(f"**Course Context:**\n{course.course_prompt}\n")
    else:
        context_parts.append("**Note:** This course doesn't have a course context set up yet. Consider advising the teacher to add one for better exercise generation.\n")
    
    # Existing exercises (titles + first 200 chars of question)
    exercises = Exercise.objects.filter(
        module__course=course,
        module__archived=False
    ).select_related('module').order_by('module__order', 'order')[:50]  # Limit to 50 most recent
    
    if exercises:
        context_parts.append("**Existing Exercises in Course:**")
        for ex in exercises:
            context_parts.append(f"- {ex.title} ({ex.exercise_type}): {ex.question[:200]}...")
        context_parts.append("")
    
    return "\n".join(context_parts)
