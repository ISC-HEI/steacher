from django.contrib import admin
from django import forms
from .models import Exercise, Answer, Course, ExerciceAsset


class ExerciceAssetForm(forms.ModelForm):
    file_upload = forms.FileField(required=False, label="Upload asset file")

    class Meta:
        model = ExerciceAsset
        fields = ('name', 'description', 'exercise')


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


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ['exercise', 'submitted_at', 'is_correct']
    list_filter = ['submitted_at', 'is_correct', 'exercise__course', 'exercise__exercise_type']
    readonly_fields = ['submitted_at']


@admin.register(ExerciceAsset)
class ExerciceAssetAdmin(admin.ModelAdmin):
    form = ExerciceAssetForm
    list_display = ('name', 'exercise', 'created_at')
    search_fields = ('name', 'description')
    list_filter = ('exercise',)
    readonly_fields = ('created_at', 'updated_at')
    fields = ('name', 'description', 'exercise', 'file_upload')

    def save_model(self, request, obj, form, change):
        uploaded_file = form.cleaned_data.get('file_upload')
        if uploaded_file:
            # If name is not provided, use the filename
            if not obj.name:
                obj.name = uploaded_file.name
            obj.content = uploaded_file.read()
        
        # If there's no file and no content, we can't save
        if not obj.content and not uploaded_file:
            # Simple way to prevent saving without content.
            # A more advanced implementation could use form validation.
            from django.contrib import messages
            messages.set_level(request, messages.ERROR)
            messages.error(request, "Cannot save an asset without content. Please upload a file.")
            return

        super().save_model(request, obj, form, change)
