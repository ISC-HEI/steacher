import json
import openai
import time
from django.conf import settings
from .models import AttemptInteraction, Exercise, Attempt, Course
import logging

client = openai.OpenAI(api_key=settings.GEMINI_API_KEY, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
logger = logging.getLogger(__name__)
MODEL_FAST = "gemini-2.5-flash"
MODEL_PRO = "gemini-2.5-pro"

def calculate_cbm_score(selections, correct_answer_ids, all_choices):
    """
    Calculates the score for a multiple-choice question using Certainty-Based Marking.
    """
    score_matrix = {
        'right': {'correct': 2, 'incorrect': -2},
        'wrong': {'correct': -1, 'incorrect': 1},
        'notsure': {'correct': 0, 'incorrect': 0}
    }

    results = {}
    total_score = 0
    max_score = 0

    all_choice_ids = [choice['id'] for choice in all_choices]

    for choice_id in all_choice_ids:
        student_confidence = selections.get(choice_id)
        is_correct_option = choice_id in correct_answer_ids

        max_score += score_matrix['right']['correct'] if is_correct_option else score_matrix['wrong']['incorrect']

        if not student_confidence:
            score = 0
            actual_status = 'missing'
        else:
            status_key = 'correct' if is_correct_option else 'incorrect'
            score = score_matrix[student_confidence][status_key]
        
        results[choice_id] = {
            'student_confidence': student_confidence,
            'actual_status': 'correct' if is_correct_option else 'wrong',
            'score': score
        }
        total_score += score

    return {
        'total_score': total_score,
        'max_score': max_score,
        'breakdown': results
    }


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
        - 'selections': the selections made by the user for a multiple-choice question, if any.
        - 'justification': the justification provided by the user, if any.
        - 'code': the code to run, if any.
        - 'query_result': the result of the query in the case of a SQL query, if any.
        - 'error_message': the error message, if any.
        - 'output': the output of the code, if any.
        - 'answer': the answer provided by the user for a multiple-choice question, if any.
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
    elif action == 'option_selected':
        selected_option = data.get('selected_option', {})
        option_id = selected_option.get('id', '')
        option_title = selected_option.get('title', '')
        user_prompt_content += f"I have chosen an option on how to solve the exercise. My choice is '{option_id}': {option_title}. Please provide instructions based on this choice."
    elif action == 'submit_answer' and exercise.exercise_type == 'multiple_choice':
        selections = data.get('selections', {})
        justification = data.get('justification', '')
        correct_answers = exercise.answer_data.get('correct_answers', [])
        all_choices = exercise.exercise_data.get('choices', [])
        
        cbm_result = calculate_cbm_score(selections, correct_answers, all_choices)
        
        score_breakdown = "\n".join(
            [
                f"- **Option {choice_id.upper()}:** I chose '{result['student_confidence']}'; the correct answer is: {result['actual_status']}. **Score: {result['score']}**"
                for choice_id, result in cbm_result['breakdown'].items()
            ]
        )
        
        user_prompt_content += (
            f"Here are my answers:\n"
            f"{score_breakdown}\n\n"
            f"**Total Score: {cbm_result['total_score']} / {cbm_result['max_score']} points.**"
        )

        if justification:
            user_prompt_content += f"\n\nMy justification was:\n{justification}"
        else:
            user_prompt_content += "\n\nI did not provide a justification."

    # For open/free-form answers on non-MC exercises (e.g., open_question), include student's answer
    elif data.get('answer') and exercise.exercise_type != 'multiple_choice':
        user_prompt_content += (
            "Here is my free-form answer to the exercise prompt:\n\n"
            f"{data.get('answer')}\n"
        )


    # add code, error message, output
    if 'code' in data:
        user_prompt_content += f"## Student code:\n```python\n{data.get('code', '')}\n```\n"

        # NEW: Run unit tests if available
        if exercise.exercise_type == 'python':
            unit_tests = exercise.answer_data.get('unit_tests', {})
            if unit_tests and unit_tests.get('test_cases'):
                from exercises.unit_testing import run_unit_tests, format_test_results_for_ai
                
                test_start_time = time.time()
                test_results = run_unit_tests(data.get('code', ''), unit_tests)
                test_duration = time.time() - test_start_time
                logger.info(f"Unit testing for exercise {exercise.id} took {test_duration:.2f} seconds.")
                
                # Add test results to the prompt for the AI
                user_prompt_content += f"\n## Unit Test Results:\n"
                user_prompt_content += format_test_results_for_ai(test_results)
                
                # Store test results in data for later saving to AttemptInteraction
                data['test_results'] = test_results
            else:
                logger.warning(f"No unit tests defined for Python exercise {exercise.id}")

    if 'error_message' in data:
        user_prompt_content += f"Error:\n```\n{data.get('error_message')}\n```"
    if 'output' in data and data.get('output'):
        user_prompt_content += f"Output:\n```\n{data.get('output')}\n```"

    if action == 'submit_answer' and exercise.exercise_type == 'multiple_choice':
        user_prompt_content = f"I chose the answer '{data.get('answer')}'."
        if data.get('justification'):
            user_prompt_content += f"\nMy justification is:\n{data.get('justification')}"
        else:
            user_prompt_content += "\nI did not provide a justification."
    
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

    # 4. Add question, expected result, correct answers, hints, additional context, choice explanations
    # TODO: refactor this to make it cleaner
    prompt += f"\n\n# Exercise"
    exercice_data = exercise.exercise_data
    if exercice_data and exercice_data.get('question'):
        prompt += f"\n\n## Question given to the student\n\n{exercice_data.get('question')}"
    
    exercise_answer_data = exercise.answer_data
    if exercise_answer_data:
        expected_result = exercise_answer_data.get('expected_result')
        if expected_result:
            prompt += f"\n\n## Expected result\n\n{expected_result}"
        correct_answers = exercise_answer_data.get('correct_answers')
        if correct_answers:
            prompt += "\n\n## Correct answers\n\n"
            for i, answer_info in enumerate(correct_answers):
                answer = answer_info.get('answer', '')
                explanation = answer_info.get('explanation')
                prompt += f"- Solution {i+1}:\n\n"

                if exercise.exercise_type in ['python', 'sql']:
                    prompt += f"```{exercise.exercise_type}\n{answer.replace('\\n', '\n')}\n```\n"
                else:
                    prompt += f"  {answer.replace('\\n', '\n')}\n"
                
                if explanation:
                    prompt += f"\n  Explanation: {explanation}\n"
        hints = exercise_answer_data.get('hints')
        if hints:
            prompt += f"\n\n## Hints that can be provided to help the student\n\n{hints}"
        additional_context = exercise_answer_data.get('additional_context')
        if additional_context:
            prompt += f"\n\n## Additional context for this exercise\n\n{additional_context}"
        
    if exercise.exercise_type == 'multiple_choice':
        prompt += f"\n\n## Explanations for each choice\n\n{exercise_answer_data.get('choice_explanations')}"

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
        assistant_content_raw = assistant_content_raw.strip()
        if assistant_content_raw.startswith("```json"):
            assistant_content_raw = assistant_content_raw[7:].strip()
            if assistant_content_raw.endswith("```"):
                assistant_content_raw = assistant_content_raw[:-3].strip()

        try:
            assistant_content_json = json.loads(assistant_content_raw)
            answer = assistant_content_json.get("answer", "")
            ambiguity = assistant_content_json.get("ambiguity", [])
            if not isinstance(ambiguity, list):
                ambiguity = [str(ambiguity)]
        except Exception as e:
            answer = assistant_content_raw
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
    system_prompt = ("""You are an AI exercise authoring assistant. You are given a json that contains the current exercise, including the exercise type, exercise data, expected result, test cases, hints, etc.
Your job is to help the teacher improve the exercise.
If you are not sure about the exercise, you can ask the teacher for clarification. Else try to improve the exercise and return the updated exercise. For exemple, you may write better hints, improve the exercise data, add more test cases, etc.
                     
# Output format                     
Your response MUST be a single JSON object with two keys:
'assistant_message' (a string explaining your changes) and
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
    if content.startswith("```"):
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

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
            updated_exercise['answer_data']['hints'] = [
                str(h.get('hint', h)) for h in hints
            ]

    return {
        'assistant_message': assistant_message,
        'updated_exercise': updated_exercise,
    }
