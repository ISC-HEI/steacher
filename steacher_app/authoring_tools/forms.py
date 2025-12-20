from django import forms
from django.db import models
from exercises.models import Course


class DocumentUploadForm(forms.Form):
    """Form for uploading documents to create exercises from."""
    
    course = forms.ModelChoiceField(
        queryset=Course.objects.none(),  # Set in __init__ based on user permissions
        required=True,
        widget=forms.Select(attrs={'class': 'select'}),
        label="Course",
        help_text="Mandatory: select the course where exercises will be created"
    )
    
    # Note: We handle multiple files manually in the view using request.FILES.getlist()
    # The form field itself doesn't need to know about multiple files
    files = forms.FileField(
        widget=forms.widgets.FileInput(attrs={
            'accept': '.pdf,.txt,.md,.csv,.json,.tex,image/*',
            'class': 'file-input',
        }),
        required=False,  # We validate in the view
        label="Upload Files",
        help_text="Maximum 50 pages total, 50MB total. Supported: PDF, TXT, MD, CSV, JSON, TEX, images (PNG, JPEG, WEBP)"
    )
    
    teacher_instructions = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'textarea',
            'rows': 4,
            'placeholder': 'Optional: Tell me about these documents (e.g., "Only extract pages 1-5" or "Only extract exercises 7-12" or "This is a midterm exam covering recursion and data structures")'
        }),
        required=False,
        label="Instructions (Optional)",
        help_text="Provide context or specific instructions about what to extract from the documents"
    )
    
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show courses where user has authoring permissions
        # Either via CourseMembership (owner/editor) or CohortMembership (teacher/owner)
        self.fields['course'].queryset = Course.objects.filter(
            models.Q(memberships__user=user, memberships__role__in=['owner', 'editor']) |
            models.Q(cohorts__memberships__user=user, cohorts__memberships__role__in=['teacher', 'owner'])
        ).distinct().order_by('name')
