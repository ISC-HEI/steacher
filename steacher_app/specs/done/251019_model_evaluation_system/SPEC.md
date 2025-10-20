# Model Evaluation System

**Date:** 2025-10-19  
**Status:** Planning Complete

## Overview

A teacher-facing tool to blindly evaluate AI guidance responses from multiple models side-by-side. Teachers create experiments via Django admin, then evaluate randomly-selected student interactions to identify which models perform best.

## Goals

- Compare current model (Gemini Flash 2.5) against OpenRouter models
- Blind evaluation: models shown as A/B/C/D, revealed only in aggregate stats
- Track which models produce highest-quality guidance responses
- Minimal friction: skip uninteresting comparisons, auto-generate next

## Architecture

### New Django App: `evaluation`

Separate from core `exercises` app for clean separation of research/analytics tooling.

### Models

**ModelEvalExperiment**
- Name, description, created_by, created_at
- ManyToMany → Exercise (which exercises to sample from)
- `model_configs` (JSON): List of OpenRouter model configurations
- `locked` (bool): Prevents editing after first comparison generated

**ModelComparisonEval**
- Links to experiment and original Trace (one comparison per trace)
- Stores conversation history, system prompt, 4 model responses
- Ranking input (e.g., "abcd" or "(ab)cd" for ties)
- Per-model and global comments
- Skipped flag

### Key Features

1. **Experiment Creation** (via admin only)
   - Select exercises to include
   - Configure OpenRouter models with quantization and reasoning parameters
   - Get "Evaluate" link to start evaluating

2. **Evaluation Flow**
   - Random trace from random exercise in experiment
   - Original response + 3 random models from experiment config
   - Shuffle into positions A/B/C/D
   - Display conversation history (server-side rendered, ChatbotPanel styling)
   - 4-column layout with responses
   - Rank via text input: "abcd" or "(ab)cd" for ties
   - Comments per model + global comment
   - Skip or Submit → auto-generate next

3. **Statistics Page**
   - Win rates per model (% ranked #1)
   - Distinguishes original vs regenerated wins
   - Total comparisons and skipped count

### Technical Details

**OpenRouter Integration**
- API endpoint: `https://openrouter.ai/api/v1/chat/completions`
- Support quantization filtering (e.g., fp8 only)
- Support reasoning tokens (effort: high/medium/low)
- Temperature 0.7 (match current guidance)
- Graceful error handling (show error in slot, reveal model name)

**Ranking Parser**
- "abcd" → {a:1, b:2, c:3, d:4}
- "(ab)cd" → {a:1, b:1, c:3, d:4} (ties)
- Validation: must rank all 4 models

**Template Strategy**
- `experiment_evaluate.html`: Standalone (no base.html for full width)
- Reuse ChatbotPanel CSS/HTML patterns for conversation display
- Server-side rendering (no Vue.js)
- Collapsible reasoning sections (like analytics page)
- 4-column responsive grid for model responses

**Access Control**
- Admin creates experiments
- Any teacher/editor can evaluate
- Auto-redirect to stats when no traces left

## Configuration

Add to `settings.py`:
```python
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '')
```

## Files Created

```
steacher_app/evaluation/
  __init__.py
  models.py          # ModelEvalExperiment, ModelComparisonEval
  views.py           # experiment_evaluate, experiment_stats
  urls.py
  admin.py           # Admin with "Evaluate" link
  openrouter.py      # OpenRouter API client
  comparison_logic.py # Generate comparisons
  ranking_parser.py  # Parse ranking input
  migrations/
  templates/evaluation/
    experiment_evaluate.html  # 4-column comparison page
    experiment_stats.html      # Win rate statistics
```

## Example Model Configs (JSON in admin)

```json
[
  {
    "name": "openai/gpt-oss-120b",
    "quantizations": ["int8"],
    "reasoning": {"effort": "high", "exclude": false}
  },
  {
    "name": "x-ai/grok-4-fast"
  },
  {
    "name": "anthropic/claude-sonnet-4.5"
  },
  {
    "name": "deepseek/deepseek-chat-v3-0324",
    "quantizations": ["int8"]
  }
]
```

## Implementation Order

1. Create app structure and models
2. OpenRouter integration
3. Comparison generation logic
4. Ranking parser
5. Views and templates
6. Admin configuration
7. Migrations and testing

## Usage Instructions

1. **Set up OpenRouter API key**:
   - Add `OPENROUTER_API_KEY` to your environment variables
   - Example: `export OPENROUTER_API_KEY="your-key-here"`

2. **Create an experiment** (via Django admin at `/admin/evaluation/modelevalexperiment/`):
   - Name: e.g., "Python Guidance Comparison"
   - Description: Optional context
   - Exercises: Select which exercises to sample from
   - Model configs: JSON array of model configurations
   
   Example model_configs:
   ```json
   [
     {
       "name": "openai/gpt-oss-120b",
       "quantizations": ["int8"],
       "reasoning": {"effort": "high", "exclude": false}
     },
     {
       "name": "x-ai/grok-4-fast"
     },
     {
       "name": "anthropic/claude-sonnet-4.5"
     },
     {
       "name": "deepseek/deepseek-chat-v3-0324",
       "quantizations": ["int8"]
     }
   ]
   ```

3. **Start evaluating**:
   - Click "Evaluate" link in admin to open the evaluation interface
   - System shows one random trace from experiment exercises
   - 4 model responses displayed as A/B/C/D (shuffled, blind)
   - Conversation history shown at top
   - Rank responses by typing: `abcd` or `(ab)cd` for ties
   - Add optional comments per model and global comment
   - Submit or Skip to continue

4. **View statistics**:
   - Click "View Stats" button during evaluation
   - Or click "Stats" link in admin
   - Shows win rates, total comparisons, model performance

## Future Enhancements (Not in Scope)

- Export comparisons to CSV
- More advanced statistics (average rank, pairwise comparisons)
- Teacher-specific API keys
- Cost tracking per model

