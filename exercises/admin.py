import html
from django import forms
from django.contrib import admin
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.utils.html import format_html, mark_safe
from django.db.models import Count
from .models import Exercise, Course, ExerciceAsset, GuidanceLog, Trace, TraceEval
from django_jsonform.widgets import JSONFormWidget

def format_guidance_logs(trace):
    """
    Formats the guidance logs for a given trace into a nice HTML representation
    that looks like a chat dialogue.
    """
    logs = trace.guidance_logs.order_by('submitted_at')
    
    # Escape all user-provided content first
    username = html.escape(trace.user.username)
    exercise_title = html.escape(trace.exercise.title)
    exercise_question = html.escape(trace.exercise.exercise_data.get('question', 'No question provided.'))
    
    html_output = f"<strong>User:</strong> {username}, <strong>Exercise:</strong> {exercise_title}<hr>"
    
    # Main container for the chat dialogue
    html_output += "<div style='padding: 10px; border: 1px solid #ccc; border-radius: 5px; background-color: #f9f9f9;'>"

    # add question text, looking like the llm response
    html_output += f"""
        <div style="display: flex; justify-content: flex-start; margin-bottom: 10px;">
            <div style="max-width: 80%; padding: 10px; border-radius: 15px; background-color: #fff; border: 1px solid #ddd;">
                <strong>Exercise Question:</strong> {exercise_question}
            </div>
        </div>
    """

    for i, log in enumerate(logs):
        interaction = log.interaction
        user_submission = interaction.get('user_submission', {})
        ai_response = interaction.get('llm_response', {})
        ai_metadata = ai_response.get('metadata', {})
        metadata = user_submission.get('metadata', {})

        # --- Build User Submission HTML (Right-aligned) ---
        submission_html = ""
        question = metadata.get('question')
        if question:
            escaped_question = html.escape(question)
            submission_html += f"<div><strong>Student's Question:</strong> {escaped_question}</div>"
        if metadata.get('action') == 'ask_hint':
            submission_html += "<div><em>Hint was requested.</em></div>"
        code = metadata.get('code')
        if code:
            language = html.escape(trace.exercise.exercise_type)
            escaped_code = html.escape(code)
            submission_html += f'<pre class="line-numbers"><code class="language-{language}">{escaped_code}</code></pre>'
        
        if submission_html:
            html_output += f"""
                <div style="display: flex; justify-content: flex-end; margin-bottom: 10px;">
                    <div style="max-width: 80%; padding: 10px; border-radius: 15px; background-color: #dcf8c6;">
                        {submission_html}
                    </div>
                </div>
            """

        # --- Build AI Feedback HTML (Left-aligned) ---
        feedback = ai_response.get('content', '')
        if feedback:
            escaped_feedback = html.escape(feedback)
            ambiguity = ai_metadata.get('ambiguity')
            ambiguity_html = ""
            if ambiguity:
                ambiguity_items = "".join([f"<li>{html.escape(str(item))}</li>" for item in ambiguity])
                ambiguity_html = f"""
                    <div style="margin-top: 10px; padding: 10px; border: 1px solid #f0ad4e; border-radius: 5px; background-color: #fcf8e3;">
                        <strong>LLM Ambiguity:</strong>
                        <ul>{ambiguity_items}</ul>
                    </div>
                """
            html_output += f"""
                <div style="display: flex; justify-content: flex-start; margin-bottom: 10px;">
                    <div style="max-width: 80%; padding: 10px; border-radius: 15px; background-color: #fff; border: 1px solid #ddd;">
                        {escaped_feedback}
                        {ambiguity_html}
                    </div>
                </div>
            """
            if '<exercise_completed>' in feedback:
                html_output += "<div><em>Exercise marked as completed by the LLM.</em></div>"

    if not logs.exists():
        html_output += "<p>No guidance logs found for this trace.</p>"
        
    html_output += "</div>" # Close main container
        
    # Use mark_safe instead of format_html since we've already escaped all user content
    return mark_safe(html_output)

LLM_PROMPTS_SCHEMA = {
    'type': 'object',
    'keys': {},
    'additionalProperties': {
        'type': 'string',
        'widget': 'textarea',
        'widget_attrs': {'rows': 20},
    }
}


class CourseAdminForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = '__all__'
        widgets = {
            'llm_prompts': JSONFormWidget(schema=LLM_PROMPTS_SCHEMA),
        }

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    form = CourseAdminForm
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
    list_display = ('id', 'version', 'exercise', 'user', 'complete', 'has_evaluation')
    list_filter = (('exercise', admin.RelatedOnlyFieldListFilter), ('user', admin.RelatedOnlyFieldListFilter), 'complete', 'version', HasEvaluationFilter)
    search_fields = ('exercise__title', 'user__username')
    inlines = [TraceEvalInline]
    readonly_fields = ('id', 'version', 'display_interactions', 'display_full_prompt')
    ordering = ['id']

    fieldsets = (
        (None, {
            'fields': ('id', 'version', 'exercise', 'user', 'complete')
        }),
        ('Interactions', {
            'fields': ('display_interactions',),
        }),
        ('Full Prompt', {
            'fields': ('display_full_prompt',),
            'classes': ('collapse',)
        }),
    )

    change_form_template = "admin/exercises/trace/change_form.html"

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(
            eval_count=Count('trace_evals')
        )
        return queryset

    def change_view(self, request, object_id, form_url='', extra_context=None):
        '''
        Add navigation arrows to the previous and next trace.
        '''
        extra_context = extra_context or {}
        
        # Get the current trace object
        obj = self.get_object(request, object_id)
        
        # Get the previous and next trace objects by id
        prev_obj = Trace.objects.filter(id__lt=obj.id).order_by('-id').first()
        next_obj = Trace.objects.filter(id__gt=obj.id).order_by('id').first()
        
        extra_context['prev_obj'] = prev_obj
        extra_context['next_obj'] = next_obj
        
        return super().change_view(
            request, object_id, form_url, extra_context=extra_context,
        )

    def response_change(self, request, obj):
        '''
        Adds navigation arrow to the next unevaluated trace.
        '''
        if "_save_and_next" in request.POST:
            next_trace = Trace.objects.filter(trace_evals__isnull=True, id__gt=obj.id).order_by('id').first()
            if next_trace:
                return HttpResponseRedirect(reverse("admin:exercises_trace_change", args=(next_trace.id,)))
            else:
                self.message_user(request, "No more unevaluated traces found.")
                return HttpResponseRedirect(reverse("admin:exercises_trace_changelist"))
        return super().response_change(request, obj)

    def has_evaluation(self, obj):
        return obj.eval_count > 0
    has_evaluation.boolean = True
    has_evaluation.short_description = 'Has Evaluation?'
    has_evaluation.admin_order_field = 'eval_count'

    def display_interactions(self, obj):
        return format_guidance_logs(obj)
    display_interactions.short_description = "Guidance Logs"

    def display_full_prompt(self, obj):
        if not obj.system_prompt:
            return "No system prompt was saved for this trace (debug mode was likely off)."

        full_prompt_str = f"----------------\n| ROLE:: SYSTEM | \n----------------\n{obj.system_prompt}\n\n"
        
        guidance_logs = obj.guidance_logs.order_by('submitted_at')
        for log in guidance_logs:
            user_submission = log.interaction.get('user_submission')
            if user_submission:
                full_prompt_str += f"----------------\n| ROLE:: {user_submission.get('role', 'user')}  | \n----------------\n{user_submission.get('content', '')}\n\n"

            llm_response = log.interaction.get('llm_response')
            if llm_response:
                full_prompt_str += f"----------------\n| ROLE:: {llm_response.get('role', 'assistant')}| \n----------------\n{llm_response.get('content', '')}\n\n"
        
        return format_html("<pre>{}</pre>", full_prompt_str)
    display_full_prompt.short_description = "Full LLM Prompt"


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
