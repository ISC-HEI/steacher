# Logic for generating model comparison evaluations.
import random
import logging
from exercises.models import Trace, Attempt
from .models import ModelEvalExperiment, ModelComparisonEval
from .openrouter import call_openrouter_model

logger = logging.getLogger(__name__)


def generate_next_comparison(experiment: ModelEvalExperiment, evaluator) -> ModelComparisonEval:
    """
    Generate the next model comparison for an experiment.
    
    Randomly selects an eligible trace from the experiment's exercises that hasn't been
    evaluated yet, reconstructs the conversation history, use the response from the original model plus
    3 random models from the experiment config, shuffles responses into A/B/C/D positions,
    and creates a ModelComparisonEval record. Locks the experiment on first comparison to
    prevent configuration changes.
    
    Args:
        experiment: The ModelEvalExperiment to generate a comparison for
        evaluator: The User performing the evaluation
        
    Returns:
        ModelComparisonEval instance with 4 model responses, or None if no eligible traces remain
    """

    # Lock experiment on first generation
    if not experiment.locked:
        experiment.locked = True
        experiment.save(update_fields=['locked'])

    # Get all eligible traces (exercise_guidance channel, from experiment exercises)
    eligible_traces = Trace.objects.filter(
        channel='exercise_guidance',
        content_type__model='attempt',
        object_id__in=Attempt.objects.filter(
            exercise__in=experiment.exercises.all()
        ).values_list('id', flat=True)
    ).exclude(
        id__in=ModelComparisonEval.objects.filter(experiment=experiment).values_list('original_trace_id', flat=True)
    )

    if not eligible_traces.exists():
        return None

    # Pick random trace
    trace = random.choice(list(eligible_traces))

    # Reconstruct conversation history up to this trace
    attempt = trace.content_object
    history = list(attempt.traces.filter(rank_order__lt=trace.rank_order).order_by('rank_order'))

    # Build message array
    messages = []
    for tr in history:
        if tr.user_content:
            messages.append({"role": "user", "content": tr.user_content})
        if tr.assistant_content:
            messages.append({"role": "assistant", "content": tr.assistant_content})
    messages.append({"role": "user", "content": trace.user_content})

    system_prompt = history[0].system_prompt if history else trace.system_prompt

    # Get original model response
    original_response = {
        'model': trace.assistant_metadata.get('model', 'gemini-2.5-flash'),
        'response': trace.assistant_content,
        'reasoning': trace.assistant_metadata.get('thoughts', []),
        'is_original': True,
        'metadata': trace.assistant_metadata,
    }

    # Pick 3 random models from experiment config
    if len(experiment.model_configs) >= 3:
        other_models = random.sample(experiment.model_configs, 3)
    else:
        other_models = experiment.model_configs

    # Generate responses
    responses = [original_response]
    for model_config in other_models:
        result = call_openrouter_model(model_config, messages, system_prompt)
        responses.append({
            'model': model_config['name'],
            'response': result['response'],
            'reasoning': result['reasoning'],
            'is_original': False,
            'metadata': result['metadata'],
        })

    # Shuffle and assign letters
    random.shuffle(responses)
    model_responses = {chr(97 + i): resp for i, resp in enumerate(responses)}

    # Create ModelComparisonEval
    comparison = ModelComparisonEval.objects.create(
        experiment=experiment,
        original_trace=trace,
        evaluator=evaluator,
        conversation_history=messages,
        system_prompt=system_prompt,
        model_responses=model_responses,
    )

    return comparison

