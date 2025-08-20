import json
import openai
import time
from django.conf import settings
from .models import GuidanceLog, Exercise, Trace
import logging

client = openai.OpenAI(api_key=settings.GEMINI_API_KEY, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
logger = logging.getLogger(__name__)
MODEL_NAME = "gemini-2.5-flash"

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

def fetch_ai_guidance(data: dict, exercise: Exercise, trace: Trace, debug: bool = False) -> dict:
    """
    Fetches AI guidance for a given exercise and trace.
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

    logger.info(f"fetch_ai_guidance: {exercise.id}, trace: {trace.id}, debug: {debug}")
    overall_start_time = time.time()

    # 1. Construct the user's message for the LLM from the incoming data
    # FIXME: this is a mess, refactor it
    user_prompt_content = ""
    action = data.get('action')
    cbm_result = None

    if action == 'ask_question':
        user_prompt_content = f"I have a specific question: {data.get('question', '')}"
    elif action == 'ask_hint':
        user_prompt_content = "I am explicitly asking for a hint."
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
        
        user_prompt_content = (
            f"Here are my answers:\n"
            f"{score_breakdown}\n\n"
            f"**Total Score: {cbm_result['total_score']} / {cbm_result['max_score']} points.**"
        )

        if justification:
            user_prompt_content += f"\n\nMy justification was:\n{justification}"
        else:
            user_prompt_content += "\n\nI did not provide a justification."


    # add code, error message, output
    if 'code' in data:
        user_prompt_content = f"## Student code:\n```python\n{data.get('code', '')}\n```\n"

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
                
                # Store test results in data for later saving to GuidanceLog
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
    guidance_logs = GuidanceLog.objects.filter(trace=trace)
    messages = []

    # 3. Add system prompt and course prompt (the specific prompt for this kind of exercise)
    with open('exercises/general_prompt.md', 'r') as file:
        prompt = file.read()

    if debug:
        prompt += f"\n\n{DEBUG_TEXT}"
    
    course_prompt = exercise.course.llm_prompts.get(exercise.exercise_type)
    if course_prompt:
        prompt += f"\n\n{course_prompt}"

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
    for log in guidance_logs.order_by('submitted_at'):
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
        trace.system_prompt = prompt
        trace.save()

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
        model=MODEL_NAME,
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

    GuidanceLog.objects.create(
        trace=trace,
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
