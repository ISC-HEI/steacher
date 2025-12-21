import io
import logging
import threading
from pathlib import Path
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction, models
from django.http import JsonResponse
from pypdf import PdfReader

from .models import AuthoringSession, UploadedFile
from .ai_logic import run_full_import_pipeline, TEXT_BASED_EXTENSIONS, ACCEPTED_UPLOAD_FORMATS
from exercises.models import Exercise, Course
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
        # Get form data
        course_id = request.POST.get('course')
        files = request.FILES.getlist('files')
        instructions = request.POST.get('teacher_instructions', '')
        
        # Validate course
        if not course_id:
            messages.error(request, "Please select a course.")
            return redirect('authoring_tools:upload')
        
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            messages.error(request, "Invalid course selected.")
            return redirect('authoring_tools:upload')
        
        # Validate files
        if not files:
            messages.error(request, "Please select at least one file.")
            return redirect('authoring_tools:upload')
        
        # Check permissions
        try:
            assert_can_edit_course(request.user, course)
        except PermissionDenied as e:
            messages.error(request, str(e))
            return redirect('authoring_tools:upload')
        
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
        
        # Validate MIME types
        for file in files:
            file_ext = Path(file.name).suffix.lower()
            
            # Allow ZIP files (will be skipped in processing for now)
            if file_ext == '.zip':
                continue
            
            # Allow text-based formats (will be converted to text/plain)
            if file_ext in TEXT_BASED_EXTENSIONS:
                continue
            
            # Check native MIME type support
            if file.content_type not in SUPPORTED_MIME_TYPES:
                messages.error(
                    request,
                    f"Unsupported file type: {file.name} ({file.content_type}). "
                    f"Supported: PDF, ZIP, TXT, MD, CSV, JSON, TEX, and images (PNG, JPEG, WEBP)."
                )
                return redirect('authoring_tools:upload')
        
        # Validate total size
        total_size = sum(f.size for f in files)
        if total_size > MAX_TOTAL_SIZE_MB * 1024 * 1024:
            messages.error(request, f"Total file size exceeds {MAX_TOTAL_SIZE_MB}MB")
            return redirect('authoring_tools:upload')
        
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
                    return redirect('authoring_tools:upload')
                
                total_pages += page_count
            
            file_data.append({
                'file': file,
                'page_count': page_count
            })
        
        if total_pages > MAX_TOTAL_PAGES:
            messages.error(request, f"Total pages ({total_pages}) exceeds {MAX_TOTAL_PAGES}")
            return redirect('authoring_tools:upload')
        
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
        
        # Start background pipeline
        thread = threading.Thread(target=run_full_import_pipeline, args=(session.id,), daemon=True)
        thread.start()
        
        messages.success(request, "Files uploaded! Analysis and exercise generation started in background.")
        return redirect('authoring_tools:review', session_id=session.id)
    
    # Check for existing active session and redirect if found
    existing = AuthoringSession.objects.filter(
        created_by=request.user,
        status__in=['analyzing', 'active']
    ).first()
    
    if existing:
        messages.info(request, "You have an ongoing import session. Please finish or abort it before starting a new one.")
        return redirect('authoring_tools:review', session_id=existing.id)
    
    # Get courses user can edit
    courses = Course.objects.filter(
        models.Q(memberships__user=request.user, memberships__role__in=['owner', 'editor']) |
        models.Q(cohorts__memberships__user=request.user, cohorts__memberships__role__in=['teacher', 'owner'])
    ).distinct().order_by('name')
    
    return render(request, 'authoring_tools/upload.html', {
        'courses': courses,
        'accepted_formats': ACCEPTED_UPLOAD_FORMATS,
    })


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
        messages.success(request, "Import aborted.")
        
    return redirect('teachers:course_detail', pk=course_pk)
