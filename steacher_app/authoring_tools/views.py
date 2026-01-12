import io
import logging
import threading
import zipfile
from pathlib import Path
from django.views.decorators.http import require_POST, require_http_methods
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction, models
from django.http import JsonResponse

from .models import AuthoringSession, UploadedFile
from .ai_logic import (
    TEXT_BASED_EXTENSIONS, ACCEPTED_UPLOAD_FORMATS,
    upload_file_to_gemini, create_or_update_cache, build_course_context_for_generator,
    SegmentationResult, MODEL
)
from exercises.models import Exercise, Course, create_trace_for
from exercises.authz import assert_can_edit_course
from .ai_logic import gemini_authoring_client
import google.genai.types as genai_types

logger = logging.getLogger(__name__)

MAX_TOTAL_SIZE_MB = 50


@login_required
def review_exercises(request, session_id):
    """Phase 3: Review extracted exercises"""
    
    session = get_object_or_404(
        AuthoringSession,
        id=session_id,
        created_by=request.user
    )
    
    # Check permissions
    try:
        assert_can_edit_course(request.user, session.course)
    except PermissionDenied as e:
        messages.error(request, str(e))
        return redirect('exercises:dashboard')
    
    if request.method == 'POST':
        # Complete session
        session.status = 'completed'
        session.save()
        messages.success(request, "Session completed!")
        return redirect('teachers:course_detail', pk=session.course.id)
    
    # AJAX request for exercise list
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        exercises = session.module.exercises.all().order_by('order') if session.module else []
        
        message_to_teacher = None
        errors_to_teacher = ""
        if session.segmentation_data:
            message_to_teacher = session.segmentation_data.get('message_to_teacher', '')
            errors_to_teacher = session.segmentation_data.get('errors_to_teacher', "")
        
        # Build map of order -> has_solution from segmentation data
        has_solution_map = {}
        if session.segmentation_data and 'exercises' in session.segmentation_data:
            for i, ex_data in enumerate(session.segmentation_data['exercises']):
                # solution is a string in SegmentedExercise; check if non-empty
                has_solution_map[i] = bool(ex_data.get('solution', '').strip())
        
        data = {
            'status': session.status,
            'course_pk': session.course.id,
            'message_to_teacher': message_to_teacher,
            'errors_to_teacher': errors_to_teacher,
            'error_message': session.error_message or '',
            'exercises': [{
                'id': ex.id,
                'title': ex.title,
                'exercise_type': ex.exercise_type,
                'is_draft': bool(ex.draft_notes), # If draft_notes is non-empty, it's a draft
                'draft_notes': ex.draft_notes,  # Include draft_notes to check for "Generating content..."
                'order': ex.order,
                'has_solution': has_solution_map.get(ex.order, False)
            } for ex in exercises]
        }
        
        return JsonResponse(data)
    
    return render(request, 'authoring_tools/review.html', {
        'session': session
    })

@login_required
@require_POST
def approve_import_notes(request, exercise_id):
    """
    Approve imported exercise by clearing the draft notes.
    This effectively marks the exercise as "Ready" in the import wizard.
    """
    exercise = get_object_or_404(Exercise, id=exercise_id)
    
    try:
        assert_can_edit_course(request.user, exercise.module.course)
    except PermissionDenied:
        return JsonResponse({'error': 'Permission denied'}, status=403)
        
    # Clear notes to mark as validated
    exercise.draft_notes = ""
    exercise.save()
    
    return JsonResponse({'is_draft': False})

@login_required
@require_POST
def abort_session(request, session_id):
    """
    Abort the import session and delete the generated module and exercises.
    """
    session = get_object_or_404(
        AuthoringSession,
        id=session_id,
        created_by=request.user
    )
    
    # Check permissions
    try:
        assert_can_edit_course(request.user, session.course)
    except PermissionDenied as e:
        messages.error(request, str(e))
        return redirect('exercises:dashboard')
        
    course_pk = session.course.id
    module = session.module
    
    # Delete session first (to detach from module if needed, though Cascade handles it differently)
    # Actually, if we delete module, session deletes via Cascade? No, session.module has on_delete=CASCADE.
    # Wait: module = ForeignKey(..., on_delete=CASCADE). This means if Module is deleted, Session is deleted.
    # So we can just delete the module.
    
    module_name = "Unknown"
    if module:
        module_name = module.name
        module.delete() # This should cascade delete the session too
        messages.success(request, f"Import aborted. Module '{module_name}' and its exercises were deleted.")
    else:
        # If no module was created yet (e.g. still analyzing), just delete the session
        session.delete()
        messages.success(request, "Import aborted. You may try restarting the process.")
        
    return redirect('teachers:course_detail', pk=course_pk)


# ============================================================================
# Question Generator Views
# ============================================================================

@login_required
def question_generator_landing(request):
    """
    Landing page for question generator - shows course selection.
    """
    # Check for existing active session
    existing = AuthoringSession.objects.filter(
        created_by=request.user,
        status__in=['active', 'building']
    ).first()
    
    if existing:
        # Redirect to appropriate page based on session state
        if existing.status == 'building' or existing.module:
            messages.info(request, "You have an ongoing session. Please finish or abort it first.")
            return redirect('authoring_tools:review', session_id=existing.id)
        else:
            # Active session - redirect to chat
            return redirect('authoring_tools:chat', session_id=existing.id)
    
    # Get courses user can edit
    courses = Course.objects.filter(
        models.Q(memberships__user=request.user, memberships__role__in=['owner', 'editor']) |
        models.Q(cohorts__memberships__user=request.user, cohorts__memberships__role__in=['teacher', 'owner'])
    ).distinct().order_by('name')
    
    # If only one course, redirect directly to it
    if courses.count() == 1:
        return redirect(f'/teacher/authoring-assistant/start/?course_id={courses.first().id}')
    
    return render(request, 'authoring_tools/landing.html', {
        'courses': courses,
    })


@login_required
def start_question_generator(request):
    """
    Start a new question generator session or redirect to existing one.
    Requires course_id parameter.
    """
    course_id = request.GET.get('course_id')
    if not course_id:
        messages.error(request, "Course ID is required.")
        return redirect('exercises:dashboard')
    
    try:
        course = Course.objects.get(id=course_id)
        assert_can_edit_course(request.user, course)
    except (Course.DoesNotExist, PermissionDenied):
        messages.error(request, "Invalid course or insufficient permissions.")
        return redirect('exercises:dashboard')
    
    # Check for existing active session
    existing = AuthoringSession.objects.filter(
        created_by=request.user,
        course=course,
        status__in=['active', 'building']
    ).first()
    
    if existing:
        # Redirect to appropriate page based on session state
        if existing.status == 'building' or existing.module:
            messages.info(request, "You have an ongoing session. Please finish or abort it first.")
            return redirect('authoring_tools:review', session_id=existing.id)
        else:
            # Active session - redirect to chat
            return redirect('authoring_tools:chat', session_id=existing.id)
    
    # Create new session
    session = AuthoringSession.objects.create(
        course=course,
        created_by=request.user,
        status='active'
    )
    
    return redirect('authoring_tools:chat', session_id=session.id)


@login_required
def question_generator_chat(request, session_id):
    """
    Question generator chat interface for a specific session.
    GET: Show chat page
    """
    session = get_object_or_404(
        AuthoringSession,
        id=session_id,
        created_by=request.user
    )
    
    # Check permissions
    try:
        assert_can_edit_course(request.user, session.course)
    except PermissionDenied as e:
        messages.error(request, str(e))
        return redirect('exercises:dashboard')
    
    # If session is building or has module, redirect to review
    if session.status == 'building' or session.module:
        messages.info(request, "Session is being built. Redirecting to review.")
        return redirect('authoring_tools:review', session_id=session.id)
    
    return render(request, 'authoring_tools/chat.html', {
        'session': session,
        'accepted_formats': ACCEPTED_UPLOAD_FORMATS,
    })


@login_required
def get_session_traces(request, session_id):
    """
    Get conversation traces for a session.
    GET: Return traces as JSON
    """
    try:
        session = get_object_or_404(AuthoringSession, id=session_id, created_by=request.user)
        
        # Check permissions
        assert_can_edit_course(request.user, session.course)
        
        # Load traces
        traces = session.traces.filter(channel='question_generator').order_by('rank_order')
        
        messages = []
        for trace in traces:
            if trace.user_content:
                # user_content is a TextField, not JSON
                messages.append({
                    'role': 'user',
                    'content': trace.user_content
                })
            if trace.assistant_content:
                messages.append({
                    'role': 'assistant',
                    'content': trace.assistant_content.get('message', '')
                })
        
        # Load uploaded files
        files = [{
            'id': f.id,
            'filename': f.filename
        } for f in session.files.all()]
        
        return JsonResponse({
            'messages': messages,
            'files': files
        })
        
    except PermissionDenied:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    except Exception as e:
        logger.error(f"Get traces error: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def chat_message(request, session_id):
    """
    Handle chat message in question generator.
    POST: Send message and get AI response
    """
    try:
        import json
        data = json.loads(request.body)
        message = data.get('message', '').strip()
        
        if not message:
            return JsonResponse({'error': 'Missing message'}, status=400)
        
        session = get_object_or_404(AuthoringSession, id=session_id, created_by=request.user)
        
        # Check permissions
        assert_can_edit_course(request.user, session.course)
        
        # Build system prompt
        teacher_lang = request.user.preferred_language or 'en'
        prompt_path = Path(__file__).parent / 'question_generator_chat_prompt.md'
        with open(prompt_path, 'r') as f:
            system_prompt = f.read().replace('{language}', teacher_lang)
        
        # Build course context
        course_context = build_course_context_for_generator(session.course)
        system_prompt = system_prompt.replace('{course_context}', course_context)
        
        print(f"--- SYSTEM PROMPT ({teacher_lang}) ---\n{system_prompt}\n-----------------------------")
        
        # Get or create cache (lazy creation on first message)
        # This is when files are uploaded to Gemini
        if not session.cache_name:
            # Upload any pending files to Gemini that don't have URIs yet
            for uploaded_file in session.files.filter(gemini_file_uri=''):
                try:
                    gemini_uri = upload_file_to_gemini(
                        uploaded_file.file_data,
                        uploaded_file.filename,
                        uploaded_file.content_type
                    )
                    uploaded_file.gemini_file_uri = gemini_uri
                    uploaded_file.save()
                except Exception as e:
                    logger.error(f"Failed to upload {uploaded_file.filename} to Gemini: {e}")
            
            cache_name = create_or_update_cache(session, system_prompt, course_context)
            session.cache_name = cache_name
            session.save()
        
        # Load conversation history from Traces
        traces = session.traces.filter(channel='question_generator').order_by('rank_order')
        conversation_history = []
        for trace in traces:
            # User message
            if trace.user_content:
                conversation_history.append({
                    'role': 'user',
                    'parts': [genai_types.Part(text=trace.user_content)]  # TextField, not JSON
                })
            # AI response
            if trace.assistant_content:
                conversation_history.append({
                    'role': 'model',
                    'parts': [genai_types.Part(text=trace.assistant_content.get('message', ''))]
                })
        
        # Add new user message
        conversation_history.append({
            'role': 'user',
            'parts': [genai_types.Part(text=message)]
        })
        
        # Call Gemini with cached content
        try:
            response = gemini_authoring_client.models.generate_content(
                model=MODEL,
                contents=conversation_history,
                config={
                    'cached_content': session.cache_name,
                    'temperature': 0.7
                }
            )
            
            assistant_message = response.text.strip()
            
        except Exception as e:
            # If cache error (e.g., cache not found or permission denied), retry without cache
            error_str = str(e)
            if 'CachedContent' in error_str or 'PERMISSION_DENIED' in error_str or '403' in error_str:
                logger.warning(f"Cache error, retrying without cache: {e}")
                session.cache_name = ''  # Clear invalid cache
                session.save()
                try:
                    response = gemini_authoring_client.models.generate_content(
                        model=MODEL,
                        contents=conversation_history,
                        config={
                            'temperature': 0.7
                        }
                    )
                    assistant_message = response.text.strip()
                except Exception as e2:
                    logger.error(f"Gemini call failed after cache retry: {e2}")
                    return JsonResponse({
                        'error': f"AI service error: {str(e2)}"
                    }, status=500)
            else:
                # Other error - retry once with cache
                logger.warning(f"First Gemini call failed, retrying: {e}")
                try:
                    response = gemini_authoring_client.models.generate_content(
                        model=MODEL,
                        contents=conversation_history,
                        config={
                            'cached_content': session.cache_name,
                            'temperature': 0.7
                        }
                    )
                    assistant_message = response.text.strip()
                except Exception as e2:
                    logger.error(f"Gemini call failed after retry: {e2}")
                    return JsonResponse({
                        'error': f"AI service error: {str(e2)}"
                    }, status=500)
        
        # Create trace for this exchange
        trace = create_trace_for(
            owner_obj=session,
            user=request.user,
            channel='question_generator',
            user_content=message,  # TextField, not JSON
            assistant_content={'message': assistant_message}
        )
        
        return JsonResponse({
            'assistant_message': assistant_message,
            'trace_id': trace.id
        })
        
    except PermissionDenied:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    except Exception as e:
        logger.error(f"Chat message error: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def upload_file(request, session_id):
    """
    Upload file during question generator session.
    POST: Upload file to Gemini and local DB
    """
    try:
        file = request.FILES.get('file')
        
        if not file:
            return JsonResponse({'error': 'Missing file'}, status=400)
        
        session = get_object_or_404(AuthoringSession, id=session_id, created_by=request.user)
        
        # Check permissions
        assert_can_edit_course(request.user, session.course)
        
        # Validate file size (50MB total limit)
        total_size = sum(f.size_bytes for f in session.files.all()) + file.size
        if total_size > MAX_TOTAL_SIZE_MB * 1024 * 1024:
            return JsonResponse({'error': f'Total file size exceeds {MAX_TOTAL_SIZE_MB}MB'}, status=400)
        
        # Read file data
        file_data = file.read()
        file_ext = Path(file.name).suffix.lower()
        
        # Handle ZIP files - extract and store individual files
        uploaded_files = []
        if file_ext == '.zip':
            try:
                with zipfile.ZipFile(io.BytesIO(file_data)) as zf:
                    for zip_info in zf.infolist():
                        # Skip directories
                        if zip_info.is_dir():
                            continue
                        
                        # Skip hidden files
                        path_parts = Path(zip_info.filename).parts
                        if any(part.startswith('.') for part in path_parts):
                            continue
                        
                        # Extract file
                        extracted_data = zf.read(zip_info.filename)
                        extracted_ext = Path(zip_info.filename).suffix.lower()
                        
                        # Determine MIME type
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
                            logger.info(f"Skipping unsupported file in ZIP: {zip_info.filename}")
                            continue
                        
                        # Store in DB (upload to Gemini happens on first chat message)
                        uploaded_file = UploadedFile.objects.create(
                            session=session,
                            filename=zip_info.filename,
                            content_type=extracted_mime,
                            file_data=extracted_data,
                            size_bytes=len(extracted_data),
                            gemini_file_uri=''  # Will be set on first chat message
                        )
                        uploaded_files.append(uploaded_file)
                        
            except zipfile.BadZipFile:
                return JsonResponse({'error': f'{file.name} is not a valid ZIP file'}, status=400)
        else:
            # Regular file (not ZIP)
            # Store in DB (upload to Gemini happens on first chat message)
            uploaded_file = UploadedFile.objects.create(
                session=session,
                filename=file.name,
                content_type=file.content_type,
                file_data=file_data,
                size_bytes=file.size,
                gemini_file_uri=''  # Will be set on first chat message
            )
            uploaded_files.append(uploaded_file)
        
        # Invalidate cache (will be recreated on next message)
        if session.cache_name:
            session.cache_name = ''
            session.save()
        
        # Return file info (no AI acknowledgment yet - happens on first chat message)
        return JsonResponse({
            'file_id': uploaded_files[0].id if uploaded_files else None,
            'filename': file.name,
            'files_extracted': len(uploaded_files)
        })
        
    except PermissionDenied:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    except Exception as e:
        logger.error(f"File upload error: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def delete_file(request, session_id, file_id):
    """
    Delete file from session.
    POST: Remove file from DB (Gemini file expires in 48h)
    """
    try:
        session = get_object_or_404(AuthoringSession, id=session_id, created_by=request.user)
        uploaded_file = get_object_or_404(UploadedFile, id=file_id, session=session)
        
        # Check permissions
        assert_can_edit_course(request.user, session.course)
        
        # Delete file
        uploaded_file.delete()
        
        # Invalidate cache (will be recreated on next message)
        if session.cache_name:
            session.cache_name = ''
            session.save()
        
        return JsonResponse({'success': True})
        
    except PermissionDenied:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    except Exception as e:
        logger.error(f"File deletion error: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def build_exercises(request, session_id):
    """
    Trigger exercise generation from conversation.
    POST: Extract exercise specs and start building
    """
    try:
        
        session = get_object_or_404(AuthoringSession, id=session_id, created_by=request.user)
        
        # Check permissions
        assert_can_edit_course(request.user, session.course)
        
        # Load last 20 messages from conversation
        traces = session.traces.filter(channel='question_generator').order_by('-rank_order')[:20]
        traces = list(reversed(traces))  # Reverse to chronological order
        
        if not traces:
            return JsonResponse({'error': 'No conversation history found'}, status=400)
        
        # Build conversation history
        conversation_history = []
        for trace in traces:
            if trace.user_content:
                conversation_history.append({
                    'role': 'user',
                    'parts': [genai_types.Part(text=trace.user_content)]  # TextField, not JSON
                })
            if trace.assistant_content:
                conversation_history.append({
                    'role': 'model',
                    'parts': [genai_types.Part(text=trace.assistant_content.get('message', ''))]
                })
        
        # Build system prompt for exercise builder
        teacher_lang = request.user.preferred_language or 'en'
        prompt_path = Path(__file__).parent / 'question_generator_build_prompt.md'
        with open(prompt_path, 'r') as f:
            build_prompt = f.read().replace('{language}', teacher_lang)
        
        course_context = build_course_context_for_generator(session.course)
        build_prompt = build_prompt.replace('{course_context}', course_context)
        
        # Add build instruction
        conversation_history.append({
            'role': 'user',
            'parts': [genai_types.Part(text=build_prompt)]
        })
        
        # Call Gemini to extract exercise specs
        # Note: We don't use cached_content here because the cache was created with a different client
        # and the full conversation history is already in conversation_history
        response = gemini_authoring_client.models.generate_content(
            model=MODEL,
            contents=conversation_history,
            config={
                'response_mime_type': 'application/json',
                'response_json_schema': SegmentationResult.model_json_schema()
            }
        )
        
        # Parse result
        segmentation_result = SegmentationResult.model_validate_json(response.text)
        
        # Check for errors
        if segmentation_result.errors_to_teacher:
            # Return error to chat interface
            create_trace_for(
                owner_obj=session,
                user=request.user,
                channel='question_generator',
                user_content='[Build Exercises clicked]',  # TextField, not JSON
                assistant_content={'message': segmentation_result.errors_to_teacher}
            )
            
            return JsonResponse({
                'error': segmentation_result.errors_to_teacher,
                'stay_on_chat': True
            })
        
        # Success - store segmentation and start Phase 2
        session.segmentation_data = segmentation_result.model_dump()
        session.status = 'building'
        session.save()
        
        # Start background thread for Phase 2 (reuse existing logic)
        from .ai_logic import build_all_exercises_async
        import asyncio
        
        def run_phase_2():
            asyncio.run(build_all_exercises_async(session.id))
        
        thread = threading.Thread(target=run_phase_2, daemon=True)
        thread.start()
        
        return JsonResponse({
            'success': True,
            'redirect_url': f'/teacher/authoring-assistant/session/{session.id}/review/'
        })
        
    except PermissionDenied:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    except Exception as e:
        logger.error(f"Build exercises error: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)
