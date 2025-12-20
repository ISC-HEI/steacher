import io
import json
import logging
import asyncio
import threading
from pathlib import Path
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from pypdf import PdfReader
from asgiref.sync import sync_to_async

from .models import AuthoringSession, UploadedFile
from .forms import DocumentUploadForm
from .ai_logic import call_gemini_for_import, build_all_exercises_async
from exercises.models import Course, Exercise, create_trace_for
from exercises.authz import assert_can_edit_course

logger = logging.getLogger(__name__)

# Suppress noisy pypdf warnings
logging.getLogger("pypdf").setLevel(logging.ERROR)

MAX_TOTAL_SIZE_MB = 50
MAX_TOTAL_PAGES = 50


@login_required
def upload_documents(request):
    """Page 1: Upload documents for import"""
    
    if request.method == 'POST':
        form = DocumentUploadForm(request.user, request.POST, request.FILES)
        
        if form.is_valid():
            course = form.cleaned_data['course']
            files = request.FILES.getlist('files')
            instructions = form.cleaned_data['teacher_instructions']
            
            # Check permissions
            try:
                assert_can_edit_course(request.user, course)
            except PermissionDenied as e:
                messages.error(request, str(e))
                return render(request, 'authoring_tools/upload.html', {'form': form})
            
            # Check for existing active session FIRST (before expensive file processing)
            existing = AuthoringSession.objects.filter(
                course=course,
                created_by=request.user,
                status__in=['analyzing', 'active']
            ).first()
            
            if existing:
                messages.warning(request, "You have an active session for this course. Completing it first.")
                existing.status = 'completed'
                existing.save()
                return redirect('authoring_tools:analysis', session_id=existing.id)
            
            # Supported MIME types (native Gemini support)
            SUPPORTED_MIME_TYPES = {
                'application/pdf',
                'text/plain',
                'text/markdown',
                'image/png',
                'image/jpeg',
                'image/webp',
                'image/heic',
                'image/heif',
            }
            
            # Text-based formats that we'll send as text/plain
            TEXT_BASED_EXTENSIONS = {'.csv', '.json', '.tex', '.txt', '.md'}
            
            # Validate MIME types
            for file in files:
                file_ext = Path(file.name).suffix.lower()
                
                # Allow text-based formats (will be converted to text/plain)
                if file_ext in TEXT_BASED_EXTENSIONS:
                    continue
                
                # Check native MIME type support
                if file.content_type not in SUPPORTED_MIME_TYPES:
                    messages.error(
                        request,
                        f"Unsupported file type: {file.name} ({file.content_type}). "
                        f"Supported: PDF, TXT, MD, CSV, JSON, TEX, and images (PNG, JPEG, WEBP)."
                    )
                    return render(request, 'authoring_tools/upload.html', {'form': form})
            
            # Validate total size
            total_size = sum(f.size for f in files)
            if total_size > MAX_TOTAL_SIZE_MB * 1024 * 1024:
                messages.error(request, f"Total file size exceeds {MAX_TOTAL_SIZE_MB}MB")
                return render(request, 'authoring_tools/upload.html', {'form': form})
            
            # Extract page counts and validate (only for PDFs)
            total_pages = 0
            file_data = []
            
            for file in files:
                page_count = None
                
                # Only check page count for PDFs
                if file.content_type == 'application/pdf':
                    try:
                        pdf = PdfReader(io.BytesIO(file.read()))
                        page_count = len(pdf.pages)
                        file.seek(0)  # Reset for later storage
                    except Exception as e:
                        messages.error(request, f"Error reading {file.name}: {str(e)}")
                        return render(request, 'authoring_tools/upload.html', {'form': form})
                    
                    total_pages += page_count
                
                file_data.append({
                    'file': file,
                    'page_count': page_count
                })
            
            if total_pages > MAX_TOTAL_PAGES:
                messages.error(request, f"Total pages ({total_pages}) exceeds {MAX_TOTAL_PAGES}")
                return render(request, 'authoring_tools/upload.html', {'form': form})
            
            # Create session and files
            with transaction.atomic():
                session = AuthoringSession.objects.create(
                    course=course,
                    created_by=request.user,
                    teacher_instructions=instructions,
                    status='analyzing'
                )
                
                for data in file_data:
                    file = data['file']
                    UploadedFile.objects.create(
                        session=session,
                        filename=file.name,
                        content_type=file.content_type,
                        file_data=file.read(),
                        size_bytes=file.size,
                        page_count=data['page_count']
                    )
            
            messages.success(request, "Files uploaded successfully!")
            return redirect('authoring_tools:analysis', session_id=session.id)
    
    else:
        form = DocumentUploadForm(request.user)
    
    return render(request, 'authoring_tools/upload.html', {'form': form})


@login_required
def analysis_session(request, session_id):
    """Page 2: Chatbot analysis and discussion"""
    
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
    
    if request.method == 'GET':
        # Load conversation history
        traces = session.traces.filter(channel='content_import').order_by('rank_order')
        
        return render(request, 'authoring_tools/analysis.html', {
            'session': session,
            'traces': traces
        })
    
    elif request.method == 'POST':
        # Handle chat message (AJAX)
        try:
            data = json.loads(request.body)
            user_message = data.get('message', '')
            
            # Call Gemini
            segmentation_result, thoughts = call_gemini_for_import(session, user_message)
            
            logger.info(f"Gemini returned {len(thoughts) if thoughts else 0} thoughts")

            # Create user trace if message is not empty (AFTER call to avoid duplication in prompt)
            if user_message:
                create_trace_for(
                    owner_obj=session,
                    user=request.user,
                    channel='content_import',
                    user_content=user_message
                )
            
            # Store segmentation in metadata along with thoughts (thoughts not shown in UI)
            assistant_metadata = {'segmentation': segmentation_result.model_dump()}
            if thoughts:
                assistant_metadata['thoughts'] = thoughts
            
            # Save the AI response as a trace
            # We add a summary in assistant_content for admin readability, though the UI uses metadata
            create_trace_for(
                owner_obj=session,
                user=request.user,
                channel='content_import',
                assistant_content={'message': 'Segmentation completed', 'summary': segmentation_result.message_to_teacher},
                assistant_metadata=assistant_metadata
            )
            
            # Store segmentation data in session for phase 2
            session.segmentation_data = segmentation_result.model_dump()
            session.save()
            
            return JsonResponse({
                'segmentation': segmentation_result.model_dump()
            })
        
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
async def create_exercises(request, session_id):
    """
    Async view that triggers Phase 2: Create exercises from segmentation data.
    Uses fire-and-forget pattern with asyncio.create_task() to build exercises in parallel.
    """
    
    # Get session (async DB query)
    @sync_to_async
    def get_session():
        return AuthoringSession.objects.select_related('course').get(
            id=session_id,
            created_by=request.user
        )
    
    try:
        session = await get_session()
    except AuthoringSession.DoesNotExist:
        messages.error(request, "Session not found.")
        return redirect('exercises:dashboard')
    
    # Check permissions (async)
    @sync_to_async
    def check_permissions():
        try:
            assert_can_edit_course(request.user, session.course)
            return True
        except PermissionDenied as e:
            return str(e)
    
    perm_result = await check_permissions()
    if perm_result is not True:
        messages.error(request, perm_result)
        return redirect('exercises:dashboard')
    
    # Validate session has segmentation data
    if not session.segmentation_data or not session.segmentation_data.get('exercises'):
        messages.error(request, "No exercises found. Please complete the analysis first.")
        return redirect('authoring_tools:analysis', session_id=session_id)
    
    # Check session status - prevent duplicate triggering
    if session.status in ['building', 'active']:
        messages.warning(request, "Exercises are already being created or have been created.")
        return redirect('authoring_tools:review', session_id=session_id)
    
    # Fire off background processing in a separate thread with its own event loop
    exercise_count = len(session.segmentation_data['exercises'])
    logger.info(f"[Phase II Async] Starting: session_id={session.id}, exercise_count={exercise_count}")
    
    def _run_in_thread(session_id):
        """Run the async function in a new thread with its own event loop"""
        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(build_all_exercises_async(session_id))
                logger.info(f"[Phase II Async] Background task completed for session {session_id}")
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"[Phase II Async] Background task failed for session {session_id}: {e}", exc_info=True)
    
    # Start in daemon thread so it doesn't block server shutdown
    thread = threading.Thread(target=_run_in_thread, args=(session.id,), daemon=True)
    thread.start()
    logger.info(f"[Phase II Async] Background thread started for session {session.id}")
    
    messages.success(
        request,
        f"✓ Creating {exercise_count} exercise(s) in parallel. "
        "This should take about 30 seconds..."
    )
    
    # Immediately redirect user to review page
    return redirect('authoring_tools:review', session_id=session_id)


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
        
        data = [{
            'id': ex.id,
            'title': ex.title,
            'exercise_type': ex.exercise_type,
            'is_draft': ex.is_draft,
            'draft_notes': ex.draft_notes,  # Include draft_notes to check for "Generating content..."
            'order': ex.order
        } for ex in exercises]
        
        return JsonResponse({'exercises': data})
    
    return render(request, 'authoring_tools/review.html', {
        'session': session
    })
