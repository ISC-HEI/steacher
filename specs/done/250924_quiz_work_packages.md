# Quizz: Work Packages

### Work Package 0 — Baseline setup and migrations
- **Goal**: Ensure dependencies, ASGI, and DB state are ready.
- **Deliverables**
  - Install: Django Channels, channels-redis, redis-py.
  - Apply migrations `0019_module_is_quiz.py`, `0020_quizlog.py`.
  - Verify `exam_project/asgi.py` and `exam_project/settings.py` enable Channels.
- **Acceptance**
  - `pip install` ok, `python manage.py migrate` ok, server runs via ASGI.

---

### Work Package 1 — Channels routing and WebSocket endpoints
- **Goal**: Define WS routes and wire into ASGI.
- **Deliverables**
  - `exercises/routing.py` with `websocket_urlpatterns`:
    - `ws/quiz/<int:cohort_id>/<int:module_id>/`
  - Include URLRouter in `exam_project/asgi.py`.
- **Acceptance**
  - WebSocket connects and closes cleanly.

---

### Work Package 2 — Redis helpers colocated in `exercises/consumers.py`
- **Goal**: Encapsulate Redis state/presence/lock; no new module.
- **Where**: Private helper section at top of `exercises/consumers.py`.
- **Deliverables**
  - Key helpers: `_state_key()`, `_presence_key()`, `_lock_key()`.
  - State API: `get_state()`, `set_state()`, `set_countdown()`, `clear_countdown()`.
  - Presence API: `add_presence()`, `presence_count()`, `presence_heartbeat()`.
  - Lock API: `acquire_lock()`, `refresh_lock()`, `has_lock()`, `release_lock_if_owner()`.
  - Atomic transitions: `start_gathering()`, `start_quiz(first_ex_id)`, `go_to_exercise(ex_id)`, `finish_question_to_results()`, `end_quiz()`.
  - TTLs: state 7200s; lock 60s; presence 30s.
  - Uses `redis.asyncio` client; connection from settings.
- **Acceptance**
  - Helper calls behave idempotently with correct TTLs.

---

### Work Package 3 — `QuizConsumer` (Channels)
- **Goal**: Single consumer for teacher and students per spec.
- **Deliverables**
  - `exercises/consumers.py` with:
    - `connect`: compute `is_teacher` once; join `quiz_{cohort_id}_{module_id}`; send current state; add presence.
    - `receive`: teacher-only commands `start_gathering`, `start_quiz`, `start_countdown`, `next_question`, `navigate_to`, `end_quiz`; students send presence heartbeats only.
    - Group handlers: `quiz_state_update`, `countdown_start`, `navigate_to`.
    - Lock enforcement + teacher heartbeat to refresh lock every 30s.
- **Acceptance**
  - Only lock holder can drive transitions; broadcasts reach all.

---

### Work Package 4 — URL endpoints and permissions
- **Goal**: Views for teacher control and student waiting.
- **Deliverables**
  - Routes:
    - Teacher control: `/teachers/cohorts/<int:cohort_id>/quiz/<int:module_id>/`
    - Student waiting: `/exercises/cohorts/<int:cohort_id>/quiz/waiting/`
  - Views enforce cohort/course permissions via `authz.py`.
- **Acceptance**
  - Pages render with correct access; unauthorized → 403.

---

### Work Package 5 — Teacher control UI per sketch
- **Goal**: Layout and behavior matching the sketch.
- **Where**: `templates/exercises/teacher/quiz_control.html`, `frontend/quiz_control.ts`.
- **Deliverables (UI)**
  - Sticky top bar with gold background:
    - Left: icon + “Quiz {module.name}”.
    - Center/right: cohort name + small presence badge.
    - Right: prominent “End quiz” button, always visible.
  - Main pane:
    - When showing a question:
      - Single-line question title.
      - Markdown-rendered question text (large content area).
      - Bottom-left: dropdown (Gathering + exercises) and “Jump” button.
      - Bottom-right primary action:
        - “Start Countdown” with seconds input (min 5, default 5) when `display_question`.
        - “Next Question” when `results_for_current_question`.
    - When showing results:
      - Horizontal split bar: correct (blue) vs incorrect (gray).
      - “Grading in progress: X of Y completed” until all graded.
- **Deliverables (TS)**
  - WS client: receive `quiz_state_update`, `countdown_start`, `navigate_to`.
  - Send commands: `start_gathering`, `start_quiz`, `start_countdown{duration}`, `next_question`, `navigate_to{exercise_id}`, `end_quiz`.
  - Poll results every 2s only during `results_for_current_question`.
- **Acceptance**
  - End quiz always reachable; jump works; primary button changes with state; results and grading counters live-update.

---

### Work Package 6 — Student waiting room UI + TS
- **Goal**: Real-time waiting room.
- **Where**: `templates/exercises/students/quiz_waiting.html`, `frontend/quiz_waiting.ts`.
- **Deliverables**
  - Live presence count; auto-redirect when state becomes `display_question`.
  - Heartbeat to maintain presence every 20s.
- **Acceptance**
  - Students see presence updates; redirect occurs instantly on quiz start.

---

### Work Package 7 — Exercise overlay and auto-submit
- **Goal**: Quiz header overlay and countdown-driven auto-submit.
- **Where**: `templates/exercises/quiz_header.html`, `templates/exercises/exercise.html`, TS files for each exercise type.
- **Deliverables**
  - Overlay shows countdown; previous/next disabled during quiz mode.
  - On countdown zero: call `window.submitAnswer()` if it hasn't been called already by student (check `window.hasAlreadySubmittedThisQuestion` flag)
  - Handle `navigate_to` to move between questions or back to waiting room.
- **Acceptance**
  - Countdown visible; auto-submit triggers at zero; navigation behaves as spec.

---

### Work Package 8 — Results polling endpoint
- **Goal**: Grading progress + correctness aggregation for teacher UI.
- **Deliverables**
  - Teachers-only JSON API for current exercise: `submissions_count`, `correct_count`, `incorrect_count`.
  - Query via `Trace` counts, detecting `<exercise_completed>` and correctness from tags/metadata.
- **Acceptance**
  - Teacher UI updates every 2s during results; bar and counters reflect DB state.

---

### Work Package 9 — Quiz lifecycle logging
- **Goal**: Persist completed quiz metadata.
- **Deliverables**
  - On quiz end, create `QuizLog` row with cohort, module, teacher, started/ended timestamps, totals.
- **Acceptance**
  - `QuizLog` row appears when ending a quiz.

---

### Work Package 10 — Permissions and guardrails
- **Goal**: Enforce roles and lock ownership.
- **Deliverables**
  - Only lock holder can execute control commands; 403 or no-op for others.
  - Student commands limited to presence heartbeats.
  - Reuse `authz.py` for teacher role checks.
- **Acceptance**
  - Unauthorized control attempts rejected and logged.

---

### Work Package 11 — Navigation and mid-quiz join
- **Goal**: Correct redirections throughout lifecycle.
- **Rules**
  - `display_question` or `results_for_current_question` → redirect students to the current exercise.
  - `gathering` → waiting room.
  - `completed` → cohort page.
- **Where**: Helpers in `exercises/views_students.py` used by waiting room and exercise views; overlay JS honors `navigate_to`.
- **Acceptance**
  - Mid-quiz joins land on the current exercise even during results; end sends all to the cohort page.

---

### Work Package 12 — Testing
- **Goal**: Confidence in core flows.
- **Deliverables**
  - Unit tests for Redis helpers (state, presence, lock, TTLs).
  - Consumer tests: connect, lock, command flow, broadcasts.
  - View tests for endpoints and JSON aggregation.
  - Minimal E2E: teacher starts quiz; students join; countdown auto-submits.
- **Acceptance**
  - Tests pass locally; linter clean.

---

### Work Package 13 — Instrumentation and logs
- **Goal**: Operability.
- **Deliverables**
  - Structured logs for transitions, lock heartbeats, countdown start/expire, errors.
  - Basic rate limits on teacher commands to prevent spam.
- **Acceptance**
  - Logs show clear lifecycle; no noisy errors in normal flow.

---

### Work Package 14 — UX polish and docs
- **Goal**: Ship-ready.
- **Deliverables**
  - UI copy and tooltips; empty states for no presence/no submissions.
  - Short guide in README or link to `specs/quiz.md` describing how to run a quiz.
- **Acceptance**
  - Teacher can run end-to-end quiz without external guidance.
