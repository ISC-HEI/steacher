from typing import Dict, Any, List
import logging
import os
from django.conf import settings
from django.template.loader import render_to_string
from django.template import engines, Engine, Context

from .models import Exercise, Attempt, Course, localized_name
from .schemas import AnswerData

logger: logging.Logger = logging.getLogger(__name__)


LANGUAGE_NAME_MAP : Dict[str, str] = {
    'en': 'English',
    'fr': 'French',
    'de': 'German',
}


def build_system_prompt(*, action: str, exercise: Exercise, attempt: Attempt) -> str:
    """
    Render the single Markdown template that composes the system prompt for the
    exercise guidance assistant, based on the provided action and exercise/attempt context.
    Student submission details (code, tests, errors, output, free-form answer) are excluded.
    """

    preferred_language_code: str = getattr(attempt.user, 'preferred_language', 'en') or 'en'
    language_name: str = LANGUAGE_NAME_MAP.get(preferred_language_code, 'English')

    # Course-level prompts
    try:
        course: Course = exercise.module.course
        override_system_prompt: str = (course.override_system_prompt or '').strip()
        course_prompt: str = (course.course_prompt or '').strip()
        exercise_type_prompt: str = (course.llm_prompts or {}).get(exercise.exercise_type)
    except Exception:
        logger.error(f"Error getting course prompts for exercise {exercise.id}")
        override_system_prompt: str = ''
        course_prompt: str = ''
        exercise_type_prompt: str = None

    # Localized exercise fields
    question_text: str = localized_name(exercise, 'question_i18n', attempt.user, lang=preferred_language_code)

    # Answer data fields
    answer_data: AnswerData = exercise.answer_data_obj if hasattr(exercise, 'answer_data_obj') else None
    expected_result = getattr(answer_data, 'expected_result', None) if answer_data else None
    hints = getattr(answer_data, 'hints', '') if answer_data else ''
    additional_context: str = getattr(answer_data, 'additional_context', '') if answer_data else ''
    image_answers: bool = getattr(exercise, 'allow_image_upload', False)

    correct_answers: List[Dict[str, Any]] = []
    if answer_data and getattr(answer_data, 'correct_answers', None):
        for ca in answer_data.correct_answers:
            correct_answers.append({
                'answer': getattr(ca, 'answer', ''),
                'explanation': getattr(ca, 'explanation', ''),
            })

    context: Dict[str, Any] = {
        'action': action,
        'is_ask_hint': action == 'ask_hint',
        'is_reveal_solution': action == 'reveal_solution',
        'exercise_type_prompt': exercise_type_prompt,
        'course_prompt': course_prompt,
        'language_name': language_name,
        'exercise_type': exercise.exercise_type,
        'question_text': question_text,
        'expected_result': expected_result,
        'correct_answers': correct_answers,
        'hints': hints,
        'additional_context': additional_context,
        'image_answers': image_answers
    }

    # If the course provides a full system prompt override, render it as a Django template string (strict, so we catch errors).
    if override_system_prompt:
        strict_engine = Engine(debug=True, string_if_invalid='[[INVALID:%s]]')
        template = strict_engine.from_string(override_system_prompt)
        # IMPORTANT: wrapping it in str, else it produces a django...SafeString that messes up the LLM
        return str(template.render(Context(context))).strip()
    else: # otherwise, render the default exercise_guidance.md template with strict engine (so we catch errors)
        tpl_path = os.path.join(settings.BASE_DIR, 'templates', 'exercises', 'prompts', 'exercise_guidance.md')
        try:
            with open(tpl_path, 'r', encoding='utf-8') as f:
                tpl_str = f.read()
            strict_engine = Engine(debug=True, string_if_invalid='[[INVALID:%s]]')
            # IMPORTANT: wrapping it in str, else it produces a django...SafeString that messes up the LLM
            return str(strict_engine.from_string(tpl_str).render(Context(context))).strip()
        except Exception as e: # return error page 
            raise Exception(f"Error rendering default exercise_guidance.md template: {e}")


