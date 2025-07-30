from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count
from .models import Exercise, Course, ExerciceAsset, GuidanceLog, Trace, TraceEval

def format_guidance_logs(trace):
    """
    Formats the guidance logs for a given trace into a nice HTML representation
    that looks like a chat dialogue.
    """
    logs = trace.guidance_logs.order_by('submitted_at')
    
    html = f"<strong>User:</strong> {trace.user.username}, <strong>Exercise:</strong> {trace.exercise.title}<hr>"
    
    # Main container for the chat dialogue
    html += "<div style='padding: 10px; border: 1px solid #ccc; border-radius: 5px; background-color: #f9f9f9;'>"

    # add question text, looking like the llm response
    html += f"""
        <div style="display: flex; justify-content: flex-start; margin-bottom: 10px;">
            <div style="max-width: 80%; padding: 10px; border-radius: 15px; background-color: #fff; border: 1px solid #ddd;">
                <strong>Exercise Question:</strong> {trace.exercise.exercise_data.get('question', 'No question provided.')}
            </div>
        </div>
    """

    for i, log in enumerate(logs):
        interaction = log.interaction
        user_submission = interaction.get('user_submission', {})
        ai_response = interaction.get('llm_response', {})
        metadata = user_submission.get('metadata', {})

        # --- Build User Submission HTML (Right-aligned) ---
        submission_html = ""
        question = metadata.get('question')
        if question:
            submission_html += f"<div><strong>Student's Question:</strong> {question}</div>"
        if metadata.get('action') == 'ask_hint':
            submission_html += "<div><em>Hint was requested.</em></div>"
        code = metadata.get('code')
        if code:
            submission_html += f'<pre style="white-space: pre-wrap; word-wrap: break-word; background-color: #d9edf7; border: 1px solid #bce8f1; padding: 10px; border-radius: 4px; margin-top: 5px;">{code}</pre>'
        
        if submission_html:
            html += f"""
                <div style="display: flex; justify-content: flex-end; margin-bottom: 10px;">
                    <div style="max-width: 80%; padding: 10px; border-radius: 15px; background-color: #dcf8c6;">
                        {submission_html}
                    </div>
                </div>
            """

        # --- Build AI Feedback HTML (Left-aligned) ---
        feedback = ai_response.get('content', '')
        if feedback:
            html += f"""
                <div style="display: flex; justify-content: flex-start; margin-bottom: 10px;">
                    <div style="max-width: 80%; padding: 10px; border-radius: 15px; background-color: #fff; border: 1px solid #ddd;">
                        {feedback}
                    </div>
                </div>
            """
            if '<exercise_completed>' in feedback:
                html += "<div><em>Exercise marked as completed by the LLM.</em></div>"

    if not logs.exists():
        html += "<p>No guidance logs found for this trace.</p>"
        
    html += "</div>" # Close main container
        
    return format_html(html)

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at', 'updated_at')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'exercise_type', 'order', 'created_at']
    list_filter = ['course', 'exercise_type', 'created_at']
    search_fields = ['title', 'description']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(ExerciceAsset)
class ExerciceAssetAdmin(admin.ModelAdmin):
    list_display = ('name', 'exercise', 'description', 'created_at')
    list_filter = ('exercise__course', 'exercise')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(GuidanceLog)
class GuidanceLogAdmin(admin.ModelAdmin):
    list_display = ('get_exercise', 'get_user', 'submitted_at')
    list_filter = ('trace__user', 'trace__exercise')
    date_hierarchy = 'submitted_at'
    ordering = ('-submitted_at',)

    def get_exercise(self, obj):
        return obj.trace.exercise
    get_exercise.short_description = 'Exercise'

    def get_user(self, obj):
        return obj.trace.user
    get_user.short_description = 'User'

class TraceEvalInlineForm(forms.ModelForm):
    class Meta:
        model = TraceEval
        fields = '__all__'
        widgets = {
            'is_ok': forms.RadioSelect(choices=[(True, 'Yes'), (False, 'No'), (None, 'Unknown')]),
        }

class TraceEvalInline(admin.TabularInline):
    model = TraceEval
    form = TraceEvalInlineForm
    extra = 1
    fields = ('is_ok', 'feedback', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')

class HasEvaluationFilter(admin.SimpleListFilter):
    title = 'has evaluation'
    parameter_name = 'has_evaluation'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Yes'),
            ('no', 'No'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(trace_evals__isnull=False).distinct()
        if self.value() == 'no':
            return queryset.filter(trace_evals__isnull=True).distinct()

@admin.register(Trace)
class TraceAdmin(admin.ModelAdmin):
    list_display = ('exercise', 'user', 'complete', 'has_evaluation')
    list_filter = ('exercise', 'user', 'complete', HasEvaluationFilter)
    search_fields = ('exercise__title', 'user__username')
    inlines = [TraceEvalInline]
    readonly_fields = ('display_interactions',)

    fieldsets = (
        (None, {
            'fields': ('exercise', 'user', 'complete')
        }),
        ('Interactions', {
            'fields': ('display_interactions',),
        }),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(
            eval_count=Count('trace_evals')
        )
        return queryset

    def has_evaluation(self, obj):
        return obj.eval_count > 0
    has_evaluation.boolean = True
    has_evaluation.short_description = 'Has Evaluation?'
    has_evaluation.admin_order_field = 'eval_count'

    def display_interactions(self, obj):
        return format_guidance_logs(obj)
    display_interactions.short_description = "Guidance Logs"

@admin.register(TraceEval)
class TraceEvalAdmin(admin.ModelAdmin):
    list_display = ('trace', 'is_ok', 'created_at')
    list_filter = ('is_ok', 'trace__exercise')
    search_fields = ('trace__exercise__title', 'trace__user__username', 'feedback')
    readonly_fields = ('created_at', 'updated_at', 'trace_details_display')
    
    fieldsets = (
        (None, {
            'fields': ('trace', 'is_ok', 'feedback')
        }),
        ('Trace Details', {
            'fields': ('trace_details_display',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['trace'].queryset = Trace.objects.filter(trace_evals__isnull=True)
        return form

    def trace_details_display(self, obj):
        if not obj.trace:
            return "Select a trace and save to see details."
        return format_guidance_logs(obj.trace)
    
    trace_details_display.short_description = "Full Trace History"
