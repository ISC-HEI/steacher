import json
import openai
import time
from django.conf import settings
from .models import AttemptInteraction, Exercise, Attempt, Course
from .schemas import ExerciseData, AnswerData, get_pydantic_schema_as_string
import logging

client = openai.OpenAI(api_key=settings.GEMINI_API_KEY, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
logger = logging.getLogger(__name__)
MODEL_FAST = "gemini-2.5-flash"
MODEL_PRO = "gemini-2.5-pro"


def _strip_markdown_fences(content: str) -> str:
    """Removes Markdown code fences (e.g., ```json) from a string."""
    content = content.strip()
    if content.startswith("```"):
        # Find the first newline
        first_newline = content.find('\n')
        if first_newline != -1:
            content = content[first_newline + 1:]
        else: # Should not happen with valid markdown but handle it
            content = content.lstrip('`')

    if content.endswith("```"):
        content = content[:-3].strip()
    return content


# used for improving the prompt
DEBUG_TEXT = """
**Output Format**
You will always respond in a JSON format with the following structure:
```json
{
  "answer": "string",
  "ambiguity": ["string"]
}
```
- `answer`: Your Socratic response to the student.
- `ambiguity`: An array of strings describing anything unclear or ambiguous in the prompt or in the given of the exercise. This is used by our AI engineers to improve the prompt. If nothing is unclear, return an empty array.
"""

def fetch_ai_guidance(data: dict, exercise: Exercise, attempt: Attempt, debug: bool = False) -> dict:
    """
    Fetches AI guidance for a given exercise and attempt.
    Input:
    - data: a dict with the following keys:
        - 'action': the action performed by the user, e.g. 'ask_question', 'ask_hint', 'submit_answer', 'run_query', 'run_code'.
        - 'question': the question to ask the AI, if any.
        - 'justification': the justification provided by the user, if any.
        - 'code': the code to run, if any.
        - 'query_result': the result of the query in the case of a SQL query, if any.
        - 'error_message': the error message, if any.
        - 'output': the output of the code, if any.
        - 'answer': the answer provided by the user, if any.
    - 'debug': a boolean flag to indicate if the debug mode is enabled. If True, the LLM will return a JSON object with the keys described in DEBUG_TEXT above.

    # TODO: refactor this data structure to make it cleaner

    Output: a dict with the following keys:
    - 'guidance': the AI-generated guidance message, as a string.
    - 'user_submission': the user's submission, as a dict in the form of an LLM message.
    - 'cbm_result': the CBM result, if any, as a dict, to help the student understand the score breakdown.
    """

    logger.info(f"fetch_ai_guidance: exercise {exercise.id}, attempt {attempt.id}, data {data}")
    overall_start_time = time.time()

    # 1. Construct the user's message for the LLM from the incoming data
    # FIXME: this is a mess, refactor it
    user_prompt_content = ""
    action = data.get('action')
    cbm_result = None

    if action == 'ask_question':
        user_prompt_content += f"I have a specific question: {data.get('question', '')}"
    elif action == 'ask_hint':
        user_prompt_content += "I am explicitly asking for a hint."

    # For open/free-form answers on non-MC exercises (e.g., open_question), include student's answer
    elif data.get('answer'):
        user_prompt_content += (
            "Here is my submitted answer:\n\n"
            f"{data.get('answer')}\n"
        )


    # add code, error message, output
    if 'code' in data:
        # Use language-specific code fences
        lang = 'python'
        try:
            if exercise.exercise_type in ['sql', 'python', 'scala']:
                lang = exercise.exercise_type
        except Exception:
            lang = 'python'
        user_prompt_content += f"## Student code:\n```{lang}\n{data.get('code', '')}\n```\n"

        # NEW: Run unit tests if available
        if exercise.exercise_type == 'python':
            unit_tests = exercise.answer_data_obj.unit_tests
            if unit_tests and unit_tests.test_cases:
                from exercises.unit_testing import run_unit_tests, format_test_results_for_ai_with_lang
                
                test_start_time = time.time()
                test_results = run_unit_tests(data.get('code', ''), unit_tests.model_dump())
                test_duration = time.time() - test_start_time
                logger.info(f"Unit testing for exercise {exercise.id} took {test_duration:.2f} seconds.")
                
                # Add test results to the prompt for the AI
                user_prompt_content += f"\n## Unit Test Results:\n"
                user_prompt_content += format_test_results_for_ai_with_lang(test_results, 'python')
                
                # Store test results in data for later saving to AttemptInteraction
                data['test_results'] = test_results
            else:
                logger.warning(f"No unit tests defined for Python exercise {exercise.id}")
        elif exercise.exercise_type == 'scala':
            unit_tests = exercise.answer_data_obj.unit_tests
            if unit_tests and unit_tests.test_cases:
                try:
                    from exercises.unit_testing import run_unit_tests_scala, format_test_results_for_ai_with_lang
                    test_start_time = time.time()
                    test_results = run_unit_tests_scala(data.get('code', ''), unit_tests.model_dump())
                    test_duration = time.time() - test_start_time
                    logger.info(f"Scala unit testing for exercise {exercise.id} took {test_duration:.2f} seconds.")
                    user_prompt_content += f"\n## Unit Test Results:\n"
                    user_prompt_content += format_test_results_for_ai_with_lang(test_results, 'scala')
                    data['test_results'] = test_results
                except Exception as e:
                    logger.warning(f"Scala unit tests failed to run: {e}")

    if 'error_message' in data:
        user_prompt_content += f"Error:\n```\n{data.get('error_message')}\n```"
    if 'output' in data and data.get('output'):
        user_prompt_content += f"Output:\n```\n{data.get('output')}\n```"

   
    #else: FIXME
    #    raise ValueError(f"Invalid action: {action}")

    # 2. Fetch conversation history
    interactions = AttemptInteraction.objects.filter(attempt=attempt)
    messages = []

    # 3. Add system prompt and course prompt (the specific prompt for this kind of exercise)
    with open('exercises/general_prompt.md', 'r') as file:
        prompt = file.read()

    if debug:
        prompt += f"\n\n{DEBUG_TEXT}"

    if action == 'ask_hint':
        prompt += """
# Hint Request Exception
For this specific request, you are allowed to relax your core directive slightly. 
The student has explicitly asked for a hint, indicating they are stuck. 
You may provide a more direct hint, such as a small code snippet, a key part of a formula, or a clearer step-by-step instruction to help them overcome their current specific obstacle. 
Do not provide the entire solution, but give them enough to make meaningful progress. Then, return to your Socratic style in subsequent interactions.
"""
    
    course_prompt = exercise.module.course.llm_prompts.get(exercise.exercise_type)
    if course_prompt:
        prompt += f"\n\n{course_prompt}"

    # Add student's preferred language directive so the tutor answers accordingly
    try:
        preferred_language_code = getattr(attempt.user, 'preferred_language', 'en') or 'en'
    except Exception:
        preferred_language_code = 'en'
    language_names = {
        'en': 'English',
        'fr': 'French',
        'de': 'German',
    }
    language_name = language_names.get(preferred_language_code, 'English')
    prompt += (
        f"\n\n## Language\n"
        f"Always respond to the student in {language_name}. "
        f"If you include code snippets, keep the code itself in its original programming language and do not translate identifiers."
    )

    # 4. Add question, expected result, correct answers, hints, additional context
    # TODO: refactor this to make it cleaner
    prompt += f"\n\n# Exercise"

    # The question is now at the top-level of the exercise object.
    q_map = getattr(exercise, 'question_i18n', {}) or {}
    if isinstance(q_map, dict):
        question_text = q_map.get(preferred_language_code) or q_map.get('en') or next(iter(q_map.values()), '')
    else:
        question_text = ''

    if question_text:
        prompt += f"\n\n## Question given to the student\n\n{question_text}"
    
    answer_data_obj = exercise.answer_data_obj
    if answer_data_obj:
        if answer_data_obj.expected_result:
            prompt += f"\n\n## Expected result\n\n{answer_data_obj.expected_result}"
        
        if answer_data_obj.correct_answers:
            prompt += "\n\n## Correct answers\n\n"
            for i, answer_info in enumerate(answer_data_obj.correct_answers):
                answer = answer_info.answer
                explanation = answer_info.explanation
                prompt += f"- Solution {i+1}:\n\n"

                if exercise.exercise_type in ['python', 'sql']:
                    prompt += f"```{exercise.exercise_type}\n{answer.replace('\\n', '\n')}\n```\n"
                else:
                    prompt += f"  {answer.replace('\\n', '\n')}\n"
                
                if explanation:
                    prompt += f"\n  Explanation: {explanation}\n"
        
        if answer_data_obj.hints:
            prompt += f"\n\n## Hints that can be provided to help the student\n\n{answer_data_obj.hints}"
        
        if answer_data_obj.additional_context:
            prompt += f"\n\n## Additional context for this exercise\n\n{answer_data_obj.additional_context}"
        
    messages.append({"role": "system", "content": prompt})

    logger.debug(f"System prompt:\n{prompt}")

    # 4. Add past messages from the log, stripping metadata to save tokens
    for log in interactions.order_by('submitted_at'):
        user_submission = log.interaction.get('user_submission')
        if user_submission:
            messages.append({
                'role': user_submission.get('role'),
                'content': user_submission.get('content')
            })
            logger.debug(f"User submission:\n{user_submission}")

        llm_response = log.interaction.get('llm_response')
        if llm_response:
            messages.append({
                'role': llm_response.get('role'),
                'content': llm_response.get('content')
            })
            logger.debug(f"LLM response:\n{llm_response}")

    # 5. Store the system prompt if in debug mode
    if debug:
        attempt.system_prompt = prompt
        attempt.save()

    # 6. Add the current user message
    user_submission = {
        "role": "user",
        "content": user_prompt_content
    }
    logger.debug(f"User prompt content:\n{user_prompt_content}")
    messages.append(user_submission)

    logger.debug(f"Messages:\n{messages}")
    

    # 7. Call the OpenAI API using JSON object response format
    llm_start_time = time.time()
    llm_response = client.chat.completions.create(
        model=MODEL_FAST,
        messages=messages,
        temperature=0.7,
        response_format={"type": "json_object"} if not debug else None,
        #max_tokens=500
    )
    llm_duration = time.time() - llm_start_time
    logger.info(f"LLM call for exercise {exercise.id} took {llm_duration:.2f} seconds.")
    logger.info(f"LLM response: model={llm_response.model}, usage={llm_response.usage}, choices={llm_response.choices}")    

    if debug:
        # parse the response as a JSON object, to obtain the answer and the *ambiguity*
        assistant_content_raw = llm_response.choices[0].message.content or ""
        assistant_content_json_str = _strip_markdown_fences(assistant_content_raw)

        try:
            assistant_content_json = json.loads(assistant_content_json_str)
            answer = assistant_content_json.get("answer", "")
            ambiguity = assistant_content_json.get("ambiguity", [])
            if not isinstance(ambiguity, list):
                ambiguity = [str(ambiguity)]
        except Exception as e:
            answer = assistant_content_json_str
            ambiguity = [f"Failed to parse JSON: {str(e)}"]
    else:        
        # just return the text of the response
        answer = (llm_response.choices[0].message.content or "").strip()

    # 7.a. Detect completion tag and mark the attempt as complete if present
    try:
        if "<exercise_completed>" in answer and not attempt.complete:
            attempt.complete = True
            attempt.save(update_fields=['complete'])
            logger.info(f"Attempt {attempt.id} marked as complete based on LLM output tag.")
    except Exception as e:
        logger.warning(f"Failed to set attempt {attempt.id} as complete: {e}")

    # 7. Create the log entry
    interaction_log = {
        "user_submission": {
            "role": "user",
            "content": user_prompt_content,
            "metadata": data
        },
        "llm_response": {
            "role": "assistant",
            "content": answer,
            "metadata": {
                "model": llm_response.model, 
                "usage": {
                     "completion_tokens": llm_response.usage.completion_tokens,
                     "prompt_tokens": llm_response.usage.prompt_tokens,
                     "total_tokens": llm_response.usage.total_tokens,
                },
                "finish_reason": llm_response.choices[0].finish_reason
            }
        }
    }
    if debug:
        interaction_log['llm_response']['metadata']['ambiguity'] = ambiguity
    
    if cbm_result:
        interaction_log['user_submission']['metadata']['cbm_result'] = cbm_result

    AttemptInteraction.objects.create(
        attempt=attempt,
        interaction=interaction_log
    )

    # 8. Prepare the data to be returned to the view
    response_data = {
        'guidance': answer,
        'user_submission': interaction_log['user_submission']
    }
    
    if cbm_result:
        response_data['cbm_result'] = cbm_result
        
    overall_duration = time.time() - overall_start_time
    logger.info(f"Total fetch_ai_guidance for exercise {exercise.id} took {overall_duration:.2f} seconds.")
    return response_data


def generate_authoring_update(*, exercise_payload: dict, messages: list, course: Course) -> dict:
    """
    Stateless helper for the teacher-facing authoring assistant.

    Input:
    - exercise_payload: current exercise DTO as seen by the form (dict)
    - messages: list of {role: 'user'|'assistant', content: str}
    - course: Course instance (for course-level prompts if any)

    Output dict:
    - 'assistant_message': str (short assistant reply)
    - 'updated_exercise': dict (complete DTO to apply on the form)
    """

    # 1) Build system prompt specialized for authoring
    system_prompt = (f"""You are an AI exercise authoring assistant. You are given a json that contains the current exercise.
Your job is to help the teacher improve the exercise. Your goal is to help a teacher create or improve an exercise. The current state of the exercise is provided to you as a JSON object under the 'Current Exercise Context' heading.
If you are not sure about the exercise or how to improve it, ask the teacher for clarification (this is a conversation, so ask for clarification if needed). 
Else try to improve the exercise and return the updated exercise. For example, you may write better hints, improve the exercise data, add more test cases, etc.
Please adhere to the following JSON structure for the 'updated_exercise' Exercise object you return. **Do not invent new fields that are not defined in the schema below.**

{get_pydantic_schema_as_string()}

# Output format
Your response MUST be a single JSON object with two keys:
'assistant_message' (a friendly and concise string explaining your changes or asking for clarification) and
'updated_exercise' (the complete, modified exercise JSON object).
Do not use markdown or code fences. The exercise object MUST be the value of the 'updated_exercise' key."""
    )

    # 2) Build a single, consolidated system prompt
    system_prompt_parts = [system_prompt]
    course_prompt = None
    try:
        # course.llm_prompts may or may not exist with keys per exercise type. Be defensive.
        exercise_type = (exercise_payload or {}).get('exercise_type')
        course_prompt = (course.llm_prompts or {}).get(exercise_type) if hasattr(course, 'llm_prompts') else None
        if course_prompt:
            system_prompt_parts.append(f"\n\n## Course-specific Instructions\n{str(course_prompt)}")
    except Exception:
        course_prompt = None

    # Provide the current exercise as a separate assistant context message to avoid user truncation
    try:
        exercise_json_str = json.dumps(exercise_payload, ensure_ascii=False, indent=2)
    except Exception:
        exercise_json_str = json.dumps({"error": "failed to serialize exercise"})
    system_prompt_parts.append(
        f"\n\n## Current Exercise Context\n"
        f"Here is the current state of the exercise you are helping the teacher with:\n"
        f"```json\n{exercise_json_str}\n```"
    )

    full_system_prompt = "\n".join(system_prompt_parts)
    messages_for_llm = [{"role": "system", "content": full_system_prompt}]


    # Append the short-lived in-page messages (user/assistant conversation)
    for m in messages:
        role = m.get('role', 'user')
        content = m.get('content', '')
        if not isinstance(content, str):
            content = str(content)
        messages_for_llm.append({"role": role, "content": content})

    # 3) Ask for a JSON object in the response, without a strict schema
    try:
        completion = client.chat.completions.create(
            model=MODEL_PRO,
            messages=messages_for_llm,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        logger.error(f"Failed to create completion for authoring assistant: {e}, messages: {messages_for_llm}")
        # Return a response that indicates failure but doesn't crash the frontend
        return {
            'assistant_message': f"Error contacting AI assistant: {e}",
            'updated_exercise': exercise_payload,
        }

    content = (completion.choices[0].message.content or '').strip()
    # Strip accidental Markdown code fencing if any
    content = _strip_markdown_fences(content)

    # 4) Parse JSON response
    def _looks_like_exercise(obj: dict) -> bool:
        if not isinstance(obj, dict):
            return False
        keys = set(obj.keys())
        if 'exercise_type' in keys and 'exercise_data' in keys:
            return True
        if 'title' in keys and ('answer_data' in keys or 'exercise_data' in keys):
            return True
        return False

    parsed: dict
    try:
        parsed = json.loads(content)
    except Exception:
        parsed = {}

    assistant_message = ''
    updated_exercise = None

    if isinstance(parsed, dict):
        # Handle common deviations gracefully
        if 'assistant_message' in parsed:
            assistant_message = parsed.get('assistant_message') or ''
        elif 'message' in parsed:
            assistant_message = parsed.get('message') or ''

        if 'updated_exercise' in parsed and isinstance(parsed['updated_exercise'], dict):
            updated_exercise = parsed['updated_exercise']
        elif 'exercise' in parsed and isinstance(parsed['exercise'], dict):
            updated_exercise = parsed['exercise']
        elif _looks_like_exercise(parsed):
            # Model returned the exercise object at top-level; adopt it
            updated_exercise = parsed

    if updated_exercise is None:
        updated_exercise = exercise_payload
    if not assistant_message:
        # As a last resort, show a generic note or echo raw content if short
        assistant_message = "Proposed changes applied." if parsed else content[:300]

    # Ensure updated_exercise remains a dict
    if not isinstance(updated_exercise, dict):
        updated_exercise = exercise_payload

    # Normalize hints to be string[] for the form, as the AI might return objects
    if 'answer_data' in updated_exercise and 'hints' in updated_exercise.get('answer_data', {}):
        hints = updated_exercise['answer_data']['hints']
        if isinstance(hints, list) and hints and isinstance(hints[0], dict):
            # It's a list of objects, flatten it to a list of strings
            updated_exercise['answer_data']['hints'] = "\n".join([
                str(h.get('hint', h)) for h in hints
            ])
        elif isinstance(hints, list):
            updated_exercise['answer_data']['hints'] = "\n".join(hints)

    return {
        'assistant_message': assistant_message,
        'updated_exercise': updated_exercise,
    }


def generate_i18n_translations(*, source_lang: str, targets: list, fields: dict, course_context: dict) -> dict:
    """Translate only i18n fields using the small model. Single-call batch.
    Returns { lang: { title?, description?, question? } }.
    Input fields are raw strings. No DB reads/writes here.
    """
    system_prompt = (
        "You are a translation engine. Translate ONLY the provided fields into each of the TARGET languages. "
        "Preserve Markdown and fenced code blocks; do not translate or alter code or placeholders (backticks, triple backticks, {{var}}). "
        "Do not add commentary.\n\n"
        "Output JSON with this exact shape:\n"
        "{\n  \"translations\": {\n    \"fr\": {\"title\": str?, \"description\": str?, \"question\": str?},\n    \"de\": {\"title\": str?, \"description\": str?, \"question\": str?}\n  }\n}\n"
        "Only include languages listed in TARGETS. Only include keys for fields that were provided in 'fields'."
    )

    payload = {
        'source_lang': source_lang,
        'targets': list(targets or []),
        'fields': {
            'title': (fields.get('title') or '').strip(),
            'description': (fields.get('description') or '').strip(),
            'question': (fields.get('question') or '').strip(),
        },
        'course_context': {
            'name': (course_context.get('name') or '').strip(),
            'description': (course_context.get('description') or '').strip(),
        }
    }

    msgs = [
        { 'role': 'system', 'content': system_prompt },
        { 'role': 'user', 'content': json.dumps(payload, ensure_ascii=False) },
    ]
    completion = client.chat.completions.create(
        model=MODEL_FAST,
        messages=msgs,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    content = (completion.choices[0].message.content or '').strip()
    content = _strip_markdown_fences(content)
    try:
        obj = json.loads(content) if content else {}
    except Exception:
        obj = {}

    translations = {}
    tmap = (obj.get('translations') or {}) if isinstance(obj, dict) else {}
    if not isinstance(tmap, dict):
        tmap = {}
    for lang in targets or []:
        entry = tmap.get(lang) or {}
        out = {}
        if isinstance(entry, dict):
            for k in ('title', 'description', 'question'):
                v = entry.get(k)
                if isinstance(v, str) and v.strip():
                    out[k] = v
        translations[lang] = out

    return translations


def generate_learning_pathway_recommendation(*, attempt: Attempt, interactions: list) -> dict:
    """
    Analyzes a student's completed attempt and generates personalized feedback
    and recommendations for the next exercise.
    """
    # 1. System Prompt Construction
    system_prompt = """You are an expert pedagogical advisor in a learning platform. Your task is to provide encouraging, personalized feedback to a student who has just completed an exercise. Based on their conversation with the AI tutor, you will also recommend the best next exercise for them to tackle from a provided list.

**Your analysis should be based on the following:**
- The full conversation history between the student and the AI tutor for the just-completed exercise. Look for signs of struggle (e.g., frequent requests for hints, repeated errors, expressions of confusion) or signs of mastery (e.g., quick correct answers, clear explanations, few interactions).
- A list of exercises in the course, including their completion status and any feedback from previous pathway recommendations.

**Output Format:**
Your response MUST be a single JSON object with the following structure. Do not include any markdown formatting or explanatory text outside of the JSON structure.

```json
{
  "performance_feedback": {
    "what_went_well": "A concise, encouraging sentence (max 25 words) highlighting a specific strength the student demonstrated. Example: 'You did a great job using the `GROUP BY` clause to aggregate the data correctly!'",
    "key_learnings": "A concise, encouraging sentence (max 25 words) summarizing the main skill or concept learned in this exercise. Example: 'This exercise was a great step in mastering how to join multiple tables.' "
  },
  "main_recommendation": {
    "exercise_id": "...",
    "title": "...",
    "what_it_is_about": "A single sentence explaining the topic of this exercise, contextualized to what the student just did. Example: 'This exercise will build on your knowledge of joins by introducing subqueries.'",
    "why_you_should_do_it": "A single sentence justifying why this is the best next step for the student. Example: 'Based on your work with joins, this is the perfect next challenge to expand your SQL skills.'"
  },
  "alternatives": [
    {
      "exercise_id": "...",
      "title": "...",
      "what_it_is_about": "...",
      "why_you_should_do_it": "...",
      "recommendation_type": "review"
    },
    {
      "exercise_id": "...",
      "title": "...",
      "what_it_is_about": "...",
      "why_you_should_do_it": "...",
      "recommendation_type": "accelerated"
    },
    {
      "exercise_id": "...",
      "title": "...",
      "what_it_is_about": "...",
      "why_you_should_do_it": "...",
      "recommendation_type": "accelerated"
    }
  ]
}
```

**Instructions for Selecting Exercises:**
1. From the provided list of `course_exercises`, select one `main_recommendation`. This should typically be the next logical exercise in the sequence, unless the student showed significant struggle or mastery.
2. Select three `alternatives`:
    - One `review` exercise: This should be an earlier exercise (a previously uncompleted one) that reinforces a concept the student seemed to struggle with. If there is no such exercise, then skip this.
    - Two `accelerated` exercises: These should be later exercises in the sequence. Choose these if the student demonstrated strong mastery and could handle a bigger jump. Don't select exercice that are very far in the sequence. If there are no such exercises, then skip this.
3. Use the `title`, `description` and `question` of the exercises to guess which ones are variants or cover similar topics. Your primary goal is to create a smooth and adaptive learning path.
4. *Important*: Never recommend an exercise that the student has already completed.
"""

    # 2. Context Gathering
    current_exercise = attempt.exercise
    course = current_exercise.module.course
    
    # Fetch the last 20 exercises in the course to provide context
    # This includes exercises before and after the current one
    all_course_exercises = Exercise.objects.filter(
        module__course=course
    ).select_related('module').order_by('module__order', 'order')

    current_exercise_index = -1
    for i, ex in enumerate(all_course_exercises):
        if ex.id == current_exercise.id:
            current_exercise_index = i
            break

    start_index = max(0, current_exercise_index - 10)
    end_index = current_exercise_index + 11  # +1 for current, +10 for after
    context_exercises = all_course_exercises[start_index:end_index]

    # Get all student attempts for these exercises to determine status
    student_attempts = Attempt.objects.filter(
        user=attempt.user,
        exercise__in=context_exercises
    ).order_by('-updated_at')

    attempts_map = {}
    for sa in student_attempts:
        if sa.exercise_id not in attempts_map:
            attempts_map[sa.exercise_id] = sa

    exercise_context_for_llm = []
    for ex in context_exercises:
        attempt_for_ex = attempts_map.get(ex.id)
        feedback = None
        if attempt_for_ex and attempt_for_ex.completion_feedback:
            feedback = attempt_for_ex.completion_feedback.get('performance_feedback')

        exercise_context_for_llm.append({
            'exercise_id': ex.id,
            'title': ex.title,
            'description': ex.description,
            'question': ex.question_i18n.get(getattr(attempt.user, 'preferred_language', 'en'), ex.question_i18n.get('en', '')),
            'status': 'completed' if attempt_for_ex and attempt_for_ex.complete else ('attempted' if attempt_for_ex else 'not_attempted'),
            'previous_pathway_feedback': feedback
        })
    
    # 3. Construct user prompt
    user_prompt = f"""
## Student's Performance Context
Here is the full conversation history for the exercise titled "{current_exercise.title}" that the student just completed.

```json
{json.dumps(interactions, indent=2)}
```

## Course Exercises Context
Here is the list of available exercises in the course for you to choose from for your recommendations.

```json
{json.dumps(exercise_context_for_llm, indent=2)}
```

Based on all this context, please generate your response in the required JSON format.
"""

    # 4. Call LLM
    messages_for_llm = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        completion = client.chat.completions.create(
            model=MODEL_FAST,  # Use the light model for speed
            messages=messages_for_llm,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        content = (completion.choices[0].message.content or '').strip()
        
        # Basic cleanup if the model wraps the response in markdown
        content = _strip_markdown_fences(content)

        response_data = json.loads(content)
        return response_data

    except Exception as e:
        logger.error(f"Failed to generate learning pathway recommendation for attempt {attempt.id}: {e}")
        # Return a sensible default or error structure if the call fails
        return {
            "error": "Failed to generate recommendation.",
            "details": str(e)
        }
