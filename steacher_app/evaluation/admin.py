from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django import forms
from .models import ModelEvalExperiment, ModelComparisonEval
from exercises.models import Exercise


class ModelEvalExperimentAdminForm(forms.ModelForm):
    class Meta:
        model = ModelEvalExperiment
        fields = '__all__'
        widgets = {
            'model_configs': forms.Textarea(attrs={'rows': 20, 'style': 'font-family: monospace; width: 100%;'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Customize the exercise field to show ID and title
        self.fields['exercises'].label_from_instance = lambda obj: f"[{obj.id}] {obj.module.course.name[:20]} - {obj.title_i18n.get('en', obj.title_i18n)}"


@admin.register(ModelEvalExperiment)
class ModelEvalExperimentAdmin(admin.ModelAdmin):
    form = ModelEvalExperimentAdminForm
    list_display = ['name', 'created_by', 'created_at', 'locked', 'evaluate_link', 'stats_link']
    filter_horizontal = ['exercises']
    readonly_fields = ['created_at']
    
    def evaluate_link(self, obj):
        if obj.id:
            url = reverse('evaluation:experiment_evaluate', args=[obj.id])
            return format_html('<a class="button" href="{}" target="_blank">Evaluate</a>', url)
        return "-"
    evaluate_link.short_description = "Evaluation Page"
    
    def stats_link(self, obj):
        if obj.id:
            url = reverse('evaluation:experiment_stats', args=[obj.id])
            return format_html('<a class="button" href="{}" target="_blank">Stats</a>', url)
        return "-"
    stats_link.short_description = "Statistics"


@admin.register(ModelComparisonEval)
class ModelComparisonEvalAdmin(admin.ModelAdmin):
    list_display = ['id', 'experiment', 'evaluator', 'created_at', 'skipped', 'ranking_input']
    list_filter = ['experiment', 'skipped', 'evaluator']
    readonly_fields = ['created_at', 'conversation_history', 'system_prompt', 'model_responses']
    search_fields = ['experiment__name', 'evaluator__email']
