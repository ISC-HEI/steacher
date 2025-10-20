from django.db import models
from exercises.models import Exercise, Trace
from accounts.models import User


class ModelEvalExperiment(models.Model):
    """
    Experiment configuration for blind side-by-side model comparisons.
    
    An experiment defines which exercises to sample from and which AI models to compare.
    Teachers create experiments via admin, then evaluate randomly-selected student interactions
    to identify which models produce the best guidance responses. Once locked (after first
    comparison is generated), the configuration cannot be modified to ensure consistency.
    """
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    exercises = models.ManyToManyField(Exercise, related_name='eval_experiments')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    locked = models.BooleanField(default=False)

    # JSON: [{"name": "openai/gpt-4o", "quantizations": ["fp8"], "reasoning": {"effort": "high", "exclude": false}}, ...]
    model_configs = models.JSONField(default=list)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Model Evaluation Experiment"
        verbose_name_plural = "Model Evaluation Experiments"


class ModelComparisonEval(models.Model):
    """
    Single blind evaluation comparing responses from multiple AI models.
    
    Each comparison takes one student interaction (Trace) and generates responses from 4 models:
    the original response that was shown to the student, plus 3 randomly-selected models from
    the experiment config. Models are shuffled and displayed as A/B/C/D. The evaluator ranks
    them without knowing which is which. Each trace can only be evaluated once per experiment
    to prevent duplicate comparisons. Results are stored for aggregate statistics.
    """
    experiment = models.ForeignKey(ModelEvalExperiment, on_delete=models.CASCADE, related_name='comparisons')
    original_trace = models.OneToOneField(Trace, on_delete=models.CASCADE)
    evaluator = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    # Store conversation history for reproducibility
    conversation_history = models.JSONField()
    system_prompt = models.TextField()

    # Model responses: {"a": {"model": "gemini-2.5-flash", "response": "...", "is_original": true, "reasoning": "...", "metadata": {}}, ...}
    model_responses = models.JSONField()

    # Ranking input (e.g., "abcd" or "(ab)cd")
    ranking_input = models.CharField(max_length=50, default='', blank=True)

    # Parsed rankings: {"a": 1, "b": 1, "c": 3, "d": 4}
    rankings = models.JSONField(default=dict, blank=True)

    # Per-model comments: {"a": "Clear but verbose", "b": "Too terse", ...}
    model_comments = models.JSONField(default=dict, blank=True)

    # Global comment
    global_comment = models.TextField(blank=True)

    # Skipped flag
    skipped = models.BooleanField(default=False)

    class Meta:
        unique_together = [['experiment', 'original_trace']]
        verbose_name = "Model Comparison Evaluation"
        verbose_name_plural = "Model Comparison Evaluations"

    def __str__(self):
        return f"Comparison {self.id} - Experiment: {self.experiment.name}"
