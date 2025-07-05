from django.contrib import admin
from .models import Exercise, Answer


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ['title', 'exercise_type', 'created_at']
    list_filter = ['exercise_type', 'created_at']
    search_fields = ['title', 'description']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ['exercise', 'submitted_at', 'is_correct']
    list_filter = ['submitted_at', 'is_correct', 'exercise__exercise_type']
    readonly_fields = ['submitted_at']
