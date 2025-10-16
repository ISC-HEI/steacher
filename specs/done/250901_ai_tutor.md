## AI Tutor Architecture and Flow

This document explains how the AI tutor currently works in Steacher. It focuses on the backend orchestration in `exercises/logic.py` and the student-facing UI in `frontend/ChatbotPanel.ts`. Use this as a guide when extending or debugging the AI tutor.

### High-level Components

- **Backend (Django)**
  - `exercises/logic.py`
    - Builds prompts and conversation history
    - Calls LLMs (Gemini/OpenAI-compatible endpoint)
    - Injects unit-test results (Python/Scala) and SQL schema context
    - Computes basic uncertainty metrics from token logprobs
    - Detects completion/solution tags and updates `Attempt`
    - Persists interactions as `Trace` rows
  - `exercises/prompting.py`
    - Generates the system prompt tailored by exercise type/action/course

- **Frontend (Vue 3 MPA)**
  - `frontend/ChatbotPanel.ts`
    - Renders conversation and AI responses
    - Cleans completion/solution tags from display
    - Triggers pathway recommendations on completion
    - Allows thumbs up/down feedback (trace evals)

## End-to-End Flow (Student Tutoring)

### 1) Student action → request payload

When a student interacts (ask question, ask hint, submit/execute code, submit open answer), the frontend sends a request to the server view handling guidance for the current `Attempt`. The view calls `fetch_ai_guidance(data, exercise, attempt)` in `exercises/logic.py`.

Input `data` includes keys like:
- **action**: `ask_question` | `ask_hint` | `submit_answer` | `run_query` | `run_code` | `reveal_solution`
- **question**: student-typed question
- **code**: code submitted (Python/SQL/Scala)
- **answer**: open question answer
- **query_result / error_message / output**: runtime context
- For SQL: **database_schema** and **foreign_keys** to inform the LLM

### 2) Prompt construction

`fetch_ai_guidance` constructs a rich user message `user_prompt_content` by:
- Encoding the student’s action (e.g., “I am explicitly asking for a hint.”)
- Embedding code in language fences when present
- For Python/Scala: running unit tests (if defined in `answer_data`) and appending results
- For SQL: appending database schema + foreign keys
- Appending any `error_message` or `output`

It then builds the system prompt via `prompting.build_system_prompt(action, exercise, attempt)`, which layers course/exercise context and pedagogy.

### 3) Conversation history from `Trace`

Prior `Trace` rows for the `Attempt` are streamed into a chat history using alternating user/model parts. This preserves the full tutoring context.

### 4) LLM call (Gemini chats)

The tutor primarily uses Gemini through the `google.genai` SDK.
- Model: `gemini-2.5-flash` for fast guidance
- Chat config:
  - `system_instruction`: the rendered system prompt
  - `temperature`: lowered to 0.2 for `reveal_solution`, else 0.7
  - `response_logprobs`: enabled with `logprobs=5` to compute uncertainty
- On exceptions, the backend returns a graceful error message to the UI.

### 5) Extract answer and update attempt

- Response text is extracted as the assistant message.
- Two control tags are recognized in the assistant output:
  - `<exercise_completed>`: marks `Attempt.complete = True`
  - `<solution_revealed>`: marks `Attempt.asked_for_solution = True`
- These tags are removed from the content before rendering on the frontend, but kept for state updates.

### 6) Uncertainty metrics (best-effort)

If token logprobs are available, `_compute_uncertainty_from_logprobs` computes aggregate metrics (avg negative log-likelihood, perplexity, top-k mass, entropy, margins). These are stored under `Trace.assistant_metadata.uncertainty`.

### 7) Persist interaction as `Trace`

The server creates a `Trace` row on the `exercise_guidance` channel with:
- `system_prompt` (only on the first trace for an attempt)
- `user_content` and `user_metadata` (the constructed prompt and original `data`)
- `assistant_content` and `assistant_metadata` (model, token usage, finish reason, timing, uncertainty)

The API returns a small payload to the frontend:
- `guidance`: assistant message (tags stripped on display)
- `user_submission`: echo of the constructed user message
- `assistant_trace_id`: for feedback/rating

## Frontend Behavior (`ChatbotPanel.ts`)

### Rendering and interaction

- Maintains an internal message list; renders user/assistant messages via Markdown (`marked`) and sanitization (`DOMPurify`).
- Hides `<exercise_completed>` and `<solution_revealed>` tags in assistant messages while preserving their side effects.
- Formats user submissions with collapsible blocks for code and answers.
- Shows a typing indicator while awaiting responses.

### Ratings (trace evals)

- Displays thumbs up/down on assistant messages with a valid `trace_id`.
- Posts to `/exercises/api/trace-eval/` with `{ trace_id, result: 'ok' | 'not_ok' }` and does an optimistic UI update.

### Completion behavior and pathway recommendation

- On first assistant message containing `<exercise_completed>`, the panel:
  - Fires confetti (suppressed if completion came from `<solution_revealed>`).
  - If a `nextExerciseUrl` exists, calls the recommendation API and renders the returned card list.

#### Recommendation request

- Route: `POST /exercises/api/attempts/{attemptId}/recommend_pathway/`
- Response shape: `{ status: 'success', data: { performance_feedback, main_recommendation, alternatives } }`
- The panel displays a “Recommended Next Step” and optional alternatives with deep links to exercises.

### Spoiler/unlock logic (solution button)

- The panel tracks submissions via `_submissionsCount` and emits `solution-unlocked` when the threshold is reached (default: 5 qualifying submissions). Parents can show a reveal-solution control based on this event.

## Learning Pathway (Backend)

The recommendation flow lives in `generate_learning_pathway_recommendation(attempt, traces)`:
- Builds a system prompt in the student’s preferred language.
- Computes lists of prior/next uncompleted exercises, factoring in student attempt status.
- Embeds the exercise context and the full tutor conversation transcript.
- Calls Gemini (`gemini-2.5-flash`) to produce structured JSON with:
  - `performance_feedback`: what went well, key learnings
  - `main_recommendation`: id/title/what/why
  - `alternatives`: up to three, typed as `review`/`accelerated`/`other`
- Persists a `Trace` on channel `learning_pathway` with the recommendation JSON in metadata.

## Authoring Assistant and i18n (Brief)

- `generate_authoring_update(...)` (teacher-facing):
  - Edit mode: returns JSON `{ assistant_message, updated_exercise }`
  - Feedback mode: returns text feedback only
  - Uses an OpenAI-compatible endpoint backed by Gemini (`MODEL_PRO`) and a strict `json_object` response expectation in edit mode.

- `generate_i18n_translations(...)`:
  - Batch translates `title/description/question` into target languages
  - Small model, deterministic settings, outputs a compact JSON map by lang.

## Data Model Touchpoints

- `Attempt`
  - Flags: `complete`, `asked_for_solution`
  - Related `Trace` history per `channel` (`exercise_guidance`, `learning_pathway`, etc.)

- `Trace`
  - `system_prompt` stored on first guidance trace
  - `user_content`/`assistant_content` and `user_metadata`/`assistant_metadata`
  - `rank_order` preserves chronology across channels

## Operational Notes

- **Models**: `MODEL_FAST = gemini-2.5-flash`, `MODEL_PRO = gemini-2.5-pro`
- **API keys**: `GEMINI_API_KEY` in settings; OpenAI client is routed to Google’s OpenAI-compatible endpoint for some features.
- **Logging**: durations for unit tests and LLM calls are logged; failures degrade gracefully.
- **Security**: All Markdown shown to students is sanitized. Do not inject raw HTML from LLM.

## Extensibility Guidelines

### Add a new student action

1. Update the view to pass a new `action` and its fields into `fetch_ai_guidance`.
2. Extend the `user_prompt_content` construction in `fetch_ai_guidance` to handle the new action.
3. If UI formatting is special, add a branch in `ChatbotPanel.formatUserMessage`.

### Adjust pedagogy or hints style

- Modify prompt templates in `exercises/prompting.py` and/or course-level prompts (`Course.llm_prompts`).
- Keep `<exercise_completed>` and `<solution_revealed>` semantics intact.

### Swap/augment LLM provider

- Centralize model names and client wiring at the top of `logic.py`.
- Ensure token usage and logprobs/uncertainty are either mapped or disabled gracefully.

### Unit tests injection

- For Python/Scala, ensure `answer_data.unit_tests` is defined; results are appended to the LLM prompt and stored in the trace metadata. Update `exercises/unit_testing.py` if test formats evolve.

### SQL schema context

- When adding/altering SQL runtime, keep `database_schema` and `foreign_keys` shape stable; the tutor relies on consistent column/type and FK structures.

## Troubleshooting

- **No guidance shown**: Check server logs for LLM errors; UI displays a generic retry message.
- **Completion didn’t trigger**: Verify assistant output contained `<exercise_completed>` and that `Attempt` updated; check message cleaning in `ChatbotPanel.displayMessage`.
- **No recommendations**: Ensure `attemptId` and `nextExerciseUrl` are present on the page; verify the POST route and server response.
- **Malformed tutor JSON (authoring/i18n)**: The code strips accidental markdown fences and falls back to safe defaults. Inspect raw content in logs.

