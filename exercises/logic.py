import json
from django.utils import timezone
import openai
from django.conf import settings
from .models import GuidanceLog, Exercise, Trace

client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)


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


def fetch_ai_guidance(data: dict, exercise: Exercise, trace: Trace) -> dict:
    """
    Fetches AI guidance for a given exercise and trace.
    Output: a dict with the following keys:
    - 'guidance': the AI-generated guidance message.
    - 'user_submission': the user's submission.
    - 'cbm_result': the CBM result, if any.
    """
    # 1. Construct the user's message for the LLM from the incoming data
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

    elif action == 'run_query':
        user_prompt_content = f"I ran this SQL query:\n```sql\n{data.get('code', '')}\n```\n"
        if data.get('error_message'):
            user_prompt_content += f"But I got an error:\n```\n{data.get('error_message')}\n```"
        else:
            user_prompt_content += f"And I got this result:\n```\n{data.get('query_result')}\n```"
    elif action == 'run_code':
        user_prompt_content = f"I ran this Python code:\n```python\n{data.get('code', '')}\n```\n"
        if data.get('error_message'):
            user_prompt_content += f"But I got an error:\n```\n{data.get('error_message')}\n```"
        else:
            user_prompt_content += f"And I got this result:\n```\n{data.get('output')}\n```"
    elif action == 'submit_answer' and exercise.exercise_type != 'multiple_choice':
        user_prompt_content = f"I chose the answer '{data.get('answer')}'."
        if data.get('justification'):
            user_prompt_content += f"\nMy justification is:\n{data.get('justification')}"
        else:
            user_prompt_content += "\nI did not provide a justification."
    else:
        raise ValueError(f"Invalid action: {action}")

    # 2. Fetch conversation history
    guidance_logs = GuidanceLog.objects.filter(trace=trace)
    messages = []

    # 3. Add system prompt
    with open('exercises/general_prompt.md', 'r') as file:
        system_prompt = file.read()
    
    course_prompt = exercise.course.llm_prompts.get(exercise.exercise_type)
    if course_prompt:
        system_prompt += f"\n\n{course_prompt}"
    
    exercise_answer_data = exercise.answer_data
    if exercise_answer_data:
        system_prompt += f"\n\nExpected result: {exercise_answer_data.get('expected_result')}"
        system_prompt += f"\n\nCorrect answers: {exercise_answer_data.get('correct_answers')}"
        system_prompt += f"\n\nHints that can be provided to help the student: {exercise_answer_data.get('hints')}"
        system_prompt += f"\n\nAdditional context for this exercise: {exercise_answer_data.get('additional_context')}"
        
    if exercise.exercise_type == 'multiple_choice':
        system_prompt += f"\n\nExplanations for each choice are: {exercise_answer_data.get('choice_explanations')}"

    messages.append({"role": "system", "content": system_prompt})

    # 4. Add past messages from the log
    for log in guidance_logs:
        messages.append(log.interaction['user_submission'])
        if 'llm_response' in log.interaction and log.interaction['llm_response']:
            messages.append(log.interaction['llm_response'])

    # 5. Add the current user message
    user_submission = {
        "role": "user",
        "content": user_prompt_content
    }
    messages.append(user_submission)

    print(f"Messages: {messages}")

    # 6. Call the OpenAI API
    llm_response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.7,
        max_tokens=500
    )
    assistant_content = llm_response.choices[0].message.content.strip()

    # 7. Create the log entry
    interaction_log = {
        "user_submission": {
            "role": "user",
            "content": user_prompt_content,
            "metadata": data
        },
        "llm_response": {
            "role": "assistant",
            "content": assistant_content,
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
    
    if cbm_result:
        interaction_log['user_submission']['metadata']['cbm_result'] = cbm_result

    GuidanceLog.objects.create(
        trace=trace,
        interaction=interaction_log
    )

    # 8. Prepare the data to be returned to the view
    response_data = {
        'guidance': assistant_content,
        'user_submission': interaction_log['user_submission']
    }
    
    if cbm_result:
        response_data['cbm_result'] = cbm_result
        
    return response_data
