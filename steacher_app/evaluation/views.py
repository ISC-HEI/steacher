from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import ModelEvalExperiment, ModelComparisonEval
from .comparison_logic import generate_next_comparison
from .ranking_parser import parse_ranking, validate_ranking


@login_required
def experiment_evaluate(request, experiment_id):
    """
    Main evaluation interface for blind model comparison.
    
    GET: Shows the current pending comparison (or generates one if none exists).
    Displays conversation history and 4 model responses labeled A/B/C/D.
    
    POST (action=skip): Marks current comparison as skipped and generates next one.
    POST (action=submit): Validates ranking input, saves evaluation with comments,
    and auto-generates the next comparison.
    
    Redirects to stats page when no more eligible traces remain.
    """
    experiment = get_object_or_404(ModelEvalExperiment, id=experiment_id)

    # Get or generate current comparison
    pending = ModelComparisonEval.objects.filter(
        experiment=experiment,
        ranking_input='',
    ).first()

    if not pending:
        pending = generate_next_comparison(experiment, request.user)
        if not pending:
            # No more traces to evaluate
            return redirect('evaluation:experiment_stats', experiment_id=experiment.id)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'skip':
            pending.skipped = True
            pending.ranking_input = 'SKIPPED'
            pending.save()
            # Generate next
            return redirect('evaluation:experiment_evaluate', experiment_id=experiment.id)

        elif action == 'submit':
            ranking_input = request.POST.get('ranking_input', '').strip()
            global_comment = request.POST.get('global_comment', '').strip()

            # Get per-model comments
            model_comments = {}
            for letter in pending.model_responses.keys():
                comment = request.POST.get(f'comment_{letter}', '').strip()
                if comment:
                    model_comments[letter] = comment

            # Validate ranking
            expected_letters = set(pending.model_responses.keys())
            is_valid, error_msg = validate_ranking(ranking_input, expected_letters)

            if not is_valid:
                return render(request, 'evaluation/experiment_evaluate.html', {
                    'experiment': experiment,
                    'comparison': pending,
                    'error': f"Invalid ranking: {error_msg}",
                })

            # Parse and save
            pending.ranking_input = ranking_input
            pending.rankings = parse_ranking(ranking_input)
            pending.global_comment = global_comment
            pending.model_comments = model_comments
            pending.save()

            # Auto-generate next
            return redirect('evaluation:experiment_evaluate', experiment_id=experiment.id)

    return render(request, 'evaluation/experiment_evaluate.html', {
        'experiment': experiment,
        'comparison': pending,
    })


@login_required
def experiment_stats(request, experiment_id):
    """
    Display aggregate statistics for an experiment.
    
    Shows win rates (percentage ranked #1) for each model that appeared in comparisons,
    distinguishing between original responses (shown to students) and regenerated responses.
    Also displays total comparison and skip counts. Models are shown by name (unblinded)
    since this is a summary view after evaluations are complete.
    """
    experiment = get_object_or_404(ModelEvalExperiment, id=experiment_id)

    comparisons = ModelComparisonEval.objects.filter(
        experiment=experiment,
        skipped=False,
    ).exclude(ranking_input='')

    # Calculate win rates
    model_stats = {}
    for comp in comparisons:
        for letter, rank in comp.rankings.items():
            model_name = comp.model_responses[letter]['model']
            if model_name not in model_stats:
                model_stats[model_name] = {'wins': 0, 'total': 0, 'is_original_wins': 0}
            model_stats[model_name]['total'] += 1
            if rank == 1:
                model_stats[model_name]['wins'] += 1
                if comp.model_responses[letter].get('is_original'):
                    model_stats[model_name]['is_original_wins'] += 1

    # Calculate win rates
    for stats in model_stats.values():
        stats['win_rate'] = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0

    return render(request, 'evaluation/experiment_stats.html', {
        'experiment': experiment,
        'model_stats': model_stats,
        'total_comparisons': comparisons.count(),
        'total_skipped': ModelComparisonEval.objects.filter(experiment=experiment, skipped=True).count(),
    })
