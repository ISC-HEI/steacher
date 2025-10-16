<!-- df568230-abb0-42b0-83ea-6f7832bb31a3 7ea2c1ad-c285-4f03-af84-3b0177c2116e -->
# Exercise Validation System

## Overview

Create a teacher-triggered system to validate exercises by:

1. Generating a taxonomy of student failure modes
2. Letting teachers review/edit failure modes
3. Simulating students with those failure modes interacting with the AI tutor
4. Judging whether the tutor handled each failure mode well
5. Providing actionable feedback to improve the exercise

## Architecture

### Data Model Changes

**1. Add `is_synthetic_student` field to User model** (`accounts/models.py`)

- Boolean field to flag synthetic users created for simulations
- Create one synthetic user and use it throught the whole simulation. Like get first user with sythetic flag true.
- Allows filtering out synthetic data from real student analytics

**2. Create `ExerciseValidation` model** (`exercises/models.py`)

- Links to Exercise being validated
- Stores failure modes taxonomy (JSON: `[{id, category, description, example}]`)
- Stores judge evaluation results (JSON: `{summary, issues: [{failure_mode_id, attempt_id, verdict, suggestion}]}`)
- Timestamps for when validation was run (just `created_at)`  

**3. Add `is_synthetic` field to Attempt model**

- Boolean flag to mark simulation attempts
- Allows queries to exclude synthetic attempts from real analytics

### Backend Views (`exercises/views_validation.py`)

**1. `exercise_validation_generate_failures` (POST)**

- Takes exercise_id
- Calls Stage 1: Failure Mode Analysis LLM prompt
- Returns JSON: `{failure_modes: [{id, category, description, example}]}`
- Stores result in ExerciseValidation model

**2. `exercise_validation_run_simulations` (POST)**

- Takes exercise_id and edited failure_modes JSON
- For each failure mode:
  - Creates synthetic user (username: `sim_ex{id}_{failure_mode_id}_{timestamp}`)
  - Runs Stage 2: Student Simulation prompt
  - Creates Attempt (with `is_synthetic=True`) and Traces via existing chat infrastructure
- Returns simulation_ids to poll for completion

**3. `exercise_validation_judge` (POST)**

- Takes exercise_id
- Retrieves all synthetic attempts for this validation run
- Runs Stage 3: Judge Evaluation prompt on each transcript
- Stores judge verdict in ExerciseValidation
- Returns JSON: `{summary, issues: [{failure_mode, verdict, suggestion}]}`

**4. `exercise_validation_status` (GET)**

- Takes exercise_id
- Returns current validation state and results for UI display

### LLM Prompts (`exercises/prompts/`)

**1. `validation_failure_modes.md`**

- Based on existing `script.py` approach
- Takes exercise definition (title, question, exercise_data, answer_data)
- Returns structured taxonomy of failure modes with concrete examples
- Running with gemini-2.5-flash-preview-09-2025, no logprobs

**2. `validation_student_sim.md`**

- Takes: exercise definition, failure mode description, tutor instructions
- Simulates a student with that specific misconception/error
- Generates realistic student messages (questions, code attempts, confusion)
- Interacts with actual AI tutor via existing guidance flow
- Running with gemini-2.5-flash-preview-09-2025, no logprobs

**3. `validation_judge.md`**

- Takes: exercise definition, failure mode, complete transcript (Traces)
- Evaluates: Socratic method maintained, misconception addressed, student progress
- Returns: verdict (good/needs_improvement/poor) and specific suggestion for exercise improvement
- Running with Gemini 2.5 Pro

### Frontend Changes

**1. Add "Simulate Students" button to `exercise_form.html`**

- Positioned near "Save & Continue Editing" button
- Opens new view (`exercise_validation.html`) with validation workflow

**2. Create validation component** (`frontend/exercise_validation.ts`)

- Stage 1 UI: Show generated failure modes with checkboxes and inline edit
- Button: "Re-generate with my notes" (adds teacher context to prompt)
- Button: "Run Simulations" (triggers stage 2)
- Stage 2 UI: Progress indicator while simulations run
- Stage 3 UI: Show judge results with expandable transcripts
- Each result shows: failure mode, verdict badge, suggestion text, link to full Attempt

**3. Update course analytics pages**

- Filter to exclude `is_synthetic=True` attempts by default
- Optional toggle to view synthetic attempts separately

### API Endpoints (`exercises/urls.py`)

```
POST /teachers/exercise/<id>/validation/generate-failures/
POST /teachers/exercise/<id>/validation/run-simulations/
POST /teachers/exercise/<id>/validation/judge/
GET  /teachers/exercise/<id>/validation/status/
```

## Implementation Strategy

### Validation Against Real Data (later)

- Later, I will test this system on exercises with existing student data
- Compare predicted failure modes against actual student Traces
- Assess whether judge evaluations align with real tutor performance
- Document validation findings to establish confidence in the system

### Performance Considerations

- Simulations can be expensive (multiple LLM calls per failure mode). 
- Run simulations in parallel (should be ok re. rate limits)
- Consider async task queue (Celery using redis) if simulations take >30s

### Open Questions for Implementation

1. There is just one synthetic users will be persist or be deleted after validation?
2. What depth of conversation for simulations (fixed N turns or until resolution)?
3. Should we limit to specific exercise types initially (Python only)?

## Key Files to Modify

- `steacher_app/accounts/models.py` - Add `is_synthetic_student` field
- `steacher_app/exercises/models.py` - Add ExerciseValidation model, `is_synthetic` to Attempt
- `steacher_app/exercises/views_validation.py` - Add 4 new validation views
- `steacher_app/exercises/urls.py` - Add validation endpoints
- `steacher_app/exercises/prompts/validation_*.md` - Create 3 new prompts
- `steacher_app/templates/exercises/teacher/exercise_form.html` - Add "Simulate" button
- `steacher_app/frontend/exercise_validation.ts` - New validation UI component
 No newline at end of file
