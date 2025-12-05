from rest_framework import serializers
from .models import Exercise, Module


class ExerciseSerializer(serializers.ModelSerializer):
    """Full serializer - includes answer_data (for admin/backend use)"""
    class Meta:
        model = Exercise
        fields = '__all__'


class ExerciseFrontendSerializer(serializers.ModelSerializer):
    """Frontend serializer - excludes answer_data"""
    class Meta:
        model = Exercise
        fields = ['id', 'title_i18n', 'description_i18n', 'question_i18n', 'exercise_type', 'exercise_data', 'created_at', 'updated_at']


class ExerciseExportSerializer(serializers.ModelSerializer):
    """Export serializer - full exercise data for import/export"""
    class Meta:
        model = Exercise
        fields = [
            'title_i18n', 'description_i18n', 'question_i18n',
            'exercise_type', 'order', 'exercise_data', 'answer_data',
            'visible', 'allow_image_upload'
        ]


class ModuleExportSerializer(serializers.ModelSerializer):
    """Export serializer - module with nested exercises"""
    exercises = ExerciseExportSerializer(many=True, read_only=True)
    
    class Meta:
        model = Module
        fields = ['name', 'description', 'order', 'visible', 'is_quiz', 'exercises']