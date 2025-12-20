from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.db.models import Q


class AuthoringSession(models.Model):
    """
    Tracks a teacher's document import session for bulk exercise creation.
    """
    STATUS_CHOICES = [
        ('analyzing', 'Analyzing'),
        ('active', 'Active'),
        ('building', 'Building'),
        ('completed', 'Completed'),
    ]
    
    course = models.ForeignKey('exercises.Course', on_delete=models.CASCADE, related_name='authoring_sessions')
    module = models.ForeignKey('exercises.Module', on_delete=models.CASCADE, null=True, blank=True, related_name='authoring_sessions', help_text="Created during Phase 2 after teacher confirms")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='authoring_sessions')
    created_at = models.DateTimeField(auto_now_add=True)
    teacher_instructions = models.TextField(
        blank=True,
        help_text="Teacher's guidance about what to extract (e.g., 'Only exercises 7-12')"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='analyzing')
    segmentation_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Latest segmentation JSON from Phase 1 (module name, exercises list)"
    )
    
    # Traces link here via GenericForeignKey for conversation history
    traces = GenericRelation('exercises.Trace', related_query_name='authoring_session_owner')
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['course', 'created_by'],
                condition=Q(status__in=['analyzing', 'active']),
                name='one_active_session_per_teacher_per_course'
            )
        ]
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['course', 'created_by', 'status'], name='authsess_crs_usr_stat_idx'),
        ]
    
    def __str__(self):
        return f"Session {self.id} - {self.course.name} by {self.created_by.username}"


class UploadedFile(models.Model):
    """
    Stores uploaded document files as binary blobs for an authoring session.
    """
    session = models.ForeignKey(AuthoringSession, related_name='files', on_delete=models.CASCADE)
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, help_text="MIME type: application/pdf, text/plain, etc.")
    file_data = models.BinaryField(help_text="Binary file content")
    size_bytes = models.IntegerField()
    page_count = models.IntegerField(null=True, blank=True, help_text="Number of pages (for PDFs only)")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['uploaded_at']
        indexes = [
            models.Index(fields=['session', 'uploaded_at'], name='upfile_session_time_idx'),
        ]
    
    def __str__(self):
        return f"{self.filename} ({self.size_bytes} bytes)"
