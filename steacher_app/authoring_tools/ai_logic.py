import io
import tempfile
import json
import logging
import asyncio
from pathlib import Path
from typing import List, Tuple
from pydantic import BaseModel, Field
from django.db.models import Max
from asgiref.sync import sync_to_async
import google.genai.types as genai_types

from exercises.logic import gemini_client, _extract_thoughts_from_response, _build_authoring_system_prompt, _parse_authoring_response
from exercises.models import Module, Exercise, create_trace_for, Course
from .models import AuthoringSession

logger = logging.getLogger(__name__)


MODEL = "gemini-3-pro-preview"


# Ensure logger outputs to console for background thread visibility
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
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
    exercises: List[SegmentedExercise] = Field(description="List of segmented exercises in document order")


def create_file_parts(session):
    """
    Create Gemini Part objects from session files for inline data.
    Returns list of Part objects that can be included in messages.
    """
    file_parts = []
    
    # Text-based extensions that should be sent as text/plain
    TEXT_BASED_EXTENSIONS = {'.csv', '.json', '.tex', '.txt', '.md'}
    
    for file in session.files.all():
        try:
            # Determine MIME type
            file_ext = Path(file.filename).suffix.lower()
            
            # Force text-based files to text/plain for Gemini compatibility
            if file_ext in TEXT_BASED_EXTENSIONS:
                mime_type = 'text/plain'
            else:
                mime_type = file.content_type or 'application/pdf'
            
            # Convert memoryview to bytes if needed
            file_data = file.file_data
            if isinstance(file_data, memoryview):
                file_data = bytes(file_data)
            
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


def call_gemini_for_import(session, user_message=None) -> Tuple[SegmentationResult, list[str]]:
    """
    Call Gemini 3 Pro to analyze documents and extract exercises with structured output.
    Returns tuple of (SegmentationResult, thoughts).
    
    If user_message is None, this is the initial analysis.
    """
    teacher_lang = session.created_by.preferred_language or 'en'
    
    # Load prompt template
    prompt_path = Path(__file__).parent / 'content_import_prompt.md'
    with open(prompt_path, 'r') as f:
        system_prompt = f.read().replace('{language}', teacher_lang)
    
    # Build conversation history
    traces = session.traces.filter(channel='content_import').order_by('rank_order')
    
    # Build messages for Gemini
    contents = []
    
    if not traces.exists():
        # Initial analysis - create file parts and send to Gemini
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
        
        contents.append({
            'role': 'user',
            'parts': parts
        })
    else:
        # Add conversation history (send files again so Gemini can re-read if needed)
        file_parts = create_file_parts(session)
        
        for trace in traces:
            if trace.user_content:
                contents.append({
                    'role': 'user',
                    'parts': [genai_types.Part(text=trace.user_content)]
                })
            if trace.assistant_metadata and 'segmentation' in trace.assistant_metadata:
                # Previous JSON response
                prev_json = trace.assistant_metadata['segmentation']
                contents.append({
                    'role': 'model',
                    'parts': [genai_types.Part(text=json.dumps(prev_json))]
                })
        
        # Add current message with file references
        if user_message:
            parts = [genai_types.Part(text=user_message)] + file_parts
            contents.append({
                'role': 'user',
                'parts': parts
            })
    
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
    Reuses prompt building and response parsing helpers from exercises.logic.
    
    Input:
    - exercise_payload: current exercise DTO as dict
    - user_message: single user message (not full conversation history)
    - course: Course instance
    - mode: 'edit' (modify exercise) or 'feedback' (provide feedback)
    
    Output:
    - assistant_message: str
    - updated_exercise: dict (complete exercise DTO)
    """
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
        
        response = await gemini_client.aio.models.generate_content(
            model=MODEL,
            contents=contents,
            config=config
        )
        
        content = (response.text or '').strip()
    except Exception as e:
        logger.error(f"Failed to create completion for authoring assistant: {e}")
        return {
            'assistant_message': f"Error contacting AI assistant: {e}",
            'updated_exercise': exercise_payload,
        }
    
    # Parse response using shared helper
    assistant_message, updated_exercise = _parse_authoring_response(content, exercise_payload, mode)
    
    return {
        'assistant_message': assistant_message,
        'updated_exercise': updated_exercise,
    }


async def build_single_exercise_async(session, module, idx, ex_data):
    """
    Build a single exercise using the async authoring assistant.
    Called in parallel via asyncio.gather().
    """
    logger.info(f"[Phase II Async] build_single_exercise: idx={idx}, title='{ex_data.get('title', 'Untitled')}'")
    
    # Create minimal draft exercise (sync DB operation)
    @sync_to_async
    def create_exercise():
        return Exercise.objects.create(
            module=module,
            order=idx,
            title_i18n={'en': ex_data['title']},
            question_i18n={'en': ex_data['content']},
            description_i18n={'en': ''},
            exercise_type='open_question',
            exercise_data={},
            answer_data={},
            is_draft=True,
            # Set a marker that we can check in the UI
            draft_notes="Generating content..." 
        )
    
    exercise = await create_exercise()
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
    
    # Call async authoring assistant
    try:
        print(f"--- [Async Thread] Calling Gemini for exercise {exercise.id}... ---")
        result = await generate_authoring_update_async(
            exercise_payload=exercise_payload,
            user_message=authoring_prompt,
            course=session.course,
            mode='edit'
        )
        print(f"--- [Async Thread] Gemini returned for exercise {exercise.id} ---")
        logger.info(f"[Phase II Async] Authoring assistant returned for exercise {exercise.id}")
        
        # Update exercise with result
        @sync_to_async
        def update_exercise():
            # Refresh from DB
            ex = Exercise.objects.get(id=exercise.id)
            
            if result and 'updated_exercise' in result:
                updates = result['updated_exercise']
                logger.info(f"[Phase II Async] Applying updates to exercise {exercise.id}")
                
                # Fields that should NEVER be updated by the AI
                protected_fields = {'id', 'pk', 'order', 'module', 'module_id', 'course', 'course_id'}
                
                for key, value in updates.items():
                    if key in protected_fields:
                        continue
                    if hasattr(ex, key):
                        setattr(ex, key, value)
                
                if 'assistant_message' in result:
                    ex.draft_notes = result['assistant_message']
                    logger.info(f"[Phase II Async] Draft notes set for exercise {exercise.id}")
                
                ex.save()
                logger.info(f"[Phase II Async] Exercise {exercise.id} saved successfully")
            else:
                logger.warning(f"[Phase II Async] No updated_exercise in result for exercise {exercise.id}")
        
        await update_exercise()
        
    except Exception as e:
        logger.error(f"[Phase II Async] Authoring assistant failed for exercise {exercise.id}: {str(e)}", exc_info=True)
        
        # Save error note
        @sync_to_async
        def save_error():
            ex = Exercise.objects.get(id=exercise.id)
            ex.draft_notes = f"Error during automatic building: {str(e)}\n\nPlease review and complete this exercise manually."
            ex.save()
        
        await save_error()
        logger.info(f"[Phase II Async] Error note saved for exercise {exercise.id}")


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
