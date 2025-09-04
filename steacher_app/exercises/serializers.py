from rest_framework import serializers
from .models import Exercise


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