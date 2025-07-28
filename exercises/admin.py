from django.contrib import admin
from .models import Exercise, Course, ExerciceAsset, GuidanceLog, Trace


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
    """Admin view for ExerciceAsset"""
    list_display = ('name', 'exercise', 'description', 'created_at')
    list_filter = ('exercise__course', 'exercise')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')

    def save_model(self, request, obj, form, change):
        if not obj.pk:  # If this is a new object
            # If content is in-memory, no need to read from disk
            # For UploadedFile, size is available.
            # For files read from disk, you might need to calculate size differently
            if hasattr(form.cleaned_data['content'], 'size'):
                obj.file_size = form.cleaned_data['content'].size
        super().save_model(request, obj, form, change)


@admin.register(GuidanceLog)
class GuidanceLogAdmin(admin.ModelAdmin):
    """Admin view for GuidanceLog"""
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


@admin.register(Trace)
class TraceAdmin(admin.ModelAdmin):
    list_display = ('exercise', 'user')
    list_filter = ('exercise', 'user')
    search_fields = ('exercise__title', 'user__username')
