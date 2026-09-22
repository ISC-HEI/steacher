# Steacher API Reference

This document lists the application-defined HTTP routes and the principal
account routes, together with their methods, authorization, and payloads.

These application endpoints connect the Steacher frontend to the Django
server. Authenticated requests use a session cookie obtained through the web
interface. Public account and mobile handoff routes use path tokens where
noted. This reference follows the implementation in this repository.

Paths containing `/api/` return JSON. Several action endpoints outside that
prefix also return JSON, as shown in the tables.

## Contents

- [Access and request format](#access-and-request-format)
- [Authentication and accounts](#authentication-and-accounts)
- [Student routes](#student-routes)
- [Guidance: the central endpoint](#guidance-the-central-endpoint)
- [Chat routes](#chat-routes)
- [Image upload routes](#image-upload-routes)
- [Quiz routes (student)](#quiz-routes-student)
- [Teacher routes](#teacher-routes)
- [Teacher JSON APIs](#teacher-json-apis)
- [Quiz routes (teacher)](#quiz-routes-teacher)
- [Authoring assistant routes](#authoring-assistant-routes)
- [Evaluation routes](#evaluation-routes)
- [Mobile routes](#mobile-routes)
- [WebSocket](#websocket)
- [Rate limits](#rate-limits)

## Access and request format

**Authorization.** The `Auth` column uses these values:

| Value | Meaning |
|---|---|
| `login` | Authenticated user; the view may also enforce object-level access |
| `course:<roles>` | Caller must hold one of these roles on the course |
| `cohort:<roles>` | Caller must hold one of these roles on the cohort |
| `token` | Unauthenticated bearer token in the path; lifetime and reuse depend on the route |
| `none` | No authentication |

Course roles are `owner`, `editor`, `viewer`. Cohort roles are `owner`,
`teacher`, `assistant`, `student`. The two are independent: a person
may author a course without teaching any cohort in it, and vice versa. The
predicates that implement this live in `steacher_app/exercises/authz.py`.

**Visibility.** A course-level role sees hidden exercises; a cohort member sees
only visible ones. Course authors can use this access to preview drafts.

**CSRF.** Session-authenticated `POST` routes require the `X-CSRFToken` header
carrying the value of the `csrftoken` cookie. The public upload submission and
magic-link send routes are marked `csrf_exempt`; the upload uses a path
token, and the magic-link route is rate limited by session and client address.

**Errors.** Most exercise JSON routes use
`{"status": "error", "message": "..."}` and preserve the usual HTTP status
meanings. A few authoring routes use the shorter `{"error": "..."}` shape.

## Authentication and accounts

Mounted at the project root.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET, POST | `/accounts/login/` | `none` | Django's session login |
| POST | `/accounts/logout/` | `login` | Ends the session |
| GET, POST | `/accounts/register/` | `none` | Invitation-gated registration |
| GET, POST | `/accounts/password_change/` | `login` | Redirects to the dashboard on success |
| GET, POST | `/accounts/password_reset/` | `none` | Sends a reset mail |
| GET, POST | `/accounts/reset/<uidb64>/<token>/` | `token` | Completes a reset |
| GET | `/reg/<token>` | `token` | Magic-link login for the mobile client |
| GET | `/admin/` | staff | Django admin |
| GET | `/` | `login` | Dashboard; detects mobile and redirects |

## Student routes

Mounted at `/exercises/`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/exercises/dashboard/` | `login` | Student dashboard |
| GET | `/exercises/about/` | `none` | Static about page |
| GET | `/exercises/<pk>/` | `login` | Exercise page; the editor and tutor panel mount here |
| GET | `/exercises/courses/<pk>/` | `login` | Course detail |
| GET | `/exercises/courses/<pk>/export/` | `login` | Exports the caller's own data for the course |
| GET | `/exercises/<exercise_id>/<filename>` | `login` | Serves an exercise asset, such as an SQL schema |
| POST | `/exercises/<exercise_id>/delete_answers/` | `login` | Clears the caller's answers for one exercise |
| POST | `/exercises/api/scala/execute/` | `login` | Runs Scala code on the interpreter service |
| POST | `/exercises/api/trace-eval/` | `login` | Records a thumbs-up or thumbs-down on one reply |
| POST | `/exercises/api/attempts/<attempt_id>/recommend_pathway/` | `login` | Requests a next-exercise recommendation |

### `POST /exercises/api/scala/execute/`

Runs a Scala submission on the isolated interpreter service.

```json
{ "code": "println(42)" }
```

Returns `success` (boolean), `output` (string), `error` (string or null),
and `durationMs` (integer). The request takes `code` and executes it within
the authenticated session, independently of an exercise. An empty submission returns HTTP 400 and an upstream
request failure returns HTTP 502. Rate limited; see [Rate limits](#rate-limits).

### `POST /exercises/api/trace-eval/`

Records a student's rating of one tutor reply.

```json
{ "trace_id": 4711, "rating": "up" }
```

`rating` is `"up"` or `"down"`.

## Guidance: the central endpoint

```
POST /exercises/<exercise_id>/attempts/<attempt_id>/guidance/
```

**Auth:** `login`. The caller must own the attempt.

This is the platform's central route: it carries a student's request through
the tutoring pipeline and returns the tutor's reply. The request body
varies by `action`, which is the field that decides how the student's situation
is described to the model.

| `action` | Meaning | Other fields read |
|---|---|---|
| `ask_question` | The student typed a question | `question` |
| `ask_hint` | The student pressed the hint button | — |
| `submit_answer` | An answer to an open question | `answer`, `image_tokens` |
| `run_submission` | A Python, SQL, Scala, or turtle submission | `code`, runtime output or error, and SQL schema fields where applicable |
| `reveal_solution` | Request for the full solution | — |

Example, a Python submission whose run produced an error:

```json
{
  "action": "run_submission",
  "code": "def f(x):\n    return x * 2\n",
  "output": "",
  "error_message": "NameError: name 'y' is not defined"
}
```

Example, a SQL submission. The browser introspects the schema out of PGlite and
sends it along, so the tutor reads the query with the tables in front of it:

```json
{
  "action": "run_submission",
  "code": "SELECT name FROM students WHERE grade > 4;",
  "query_result": "{\n  \"type\": \"rows\",\n  \"rows\": [{ \"name\": \"Ada\" }]\n}",
  "database_schema": {
    "students": [
      { "column_name": "id",    "data_type": "integer" },
      { "column_name": "name",  "data_type": "text" },
      { "column_name": "grade", "data_type": "numeric" }
    ]
  },
  "foreign_keys": {}
}
```

**Response.**

```json
{
  "status": "success",
  "guidance": "Your WHERE clause filters on grade, which is right. What does...",
  "user_submission": { "role": "user", "content": "..." },
  "assistant_trace_id": 4711
}
```

`user_submission.images` contains image tokens and `has_highlights` flags.
For course owners and editors, the response can also include `thoughts` and
`debug_fields` (transcription, error description, and guidance). The view removes
those two fields for other users. Highlighted images are served through
the dedicated image route.

**Solution gating.** `action: "reveal_solution"` is checked on the server
against traces on the same attempt with channel `exercise_guidance` and action
`run_submission` or `submit_answer`. Hints and questions do not count.
Below five submissions, the route returns HTTP 200 with an unlock reminder
and leaves the trace history unchanged:

```json
{ "status": "success", "guidance": "Spoiler locked: make 5 submissions to unlock." }
```

The server applies the submission threshold to `reveal_solution`. The prompt
template defines the tutoring policy for questions, hints, and submissions.

**Completion.** When the tutor judges the exercise finished it emits the literal
marker `<exercise_completed>` in its reply. The server scans for it, flips the
attempt's completion flag, and passes the text through unchanged; the page
strips the marker before rendering the reply.

**Interaction records.** Each guidance call that reaches trace persistence
writes one trace row before returning the reply, including fallback replies
from the provider error handler. The row holds the rendered system prompt on the first turn, the
student's message, the structured reply, token accounting, and latency.

## Chat routes

A study chat independent of any single exercise.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/exercises/chat/` | `login` | Chat home |
| GET, POST | `/exercises/chat/threads/` | `login` | Lists threads; `POST` creates one |
| GET | `/exercises/chat/threads/<thread_id>/` | `login` | Messages in one thread |
| POST | `/exercises/chat/threads/<thread_id>/send/` | `login` | Sends a message and returns the reply |
| POST | `/exercises/chat/threads/<thread_id>/delete/` | `login` | Deletes the thread |

## Image upload routes

A two-device flow: the student requests a token on the desktop, opens the
matching URL on a phone, and uploads a photograph of handwritten work.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/exercises/image/upload-token/` | `login` | Mints a single-use upload token |
| GET | `/exercises/upload/<token>/` | `token` | The phone-facing upload page |
| POST | `/exercises/upload/<token>/submit/` | `token` | Receives the photograph. `csrf_exempt` |
| GET | `/exercises/image/image-status/<token>/` | `login` | Polled by the desktop page while it waits |
| GET | `/exercises/image/<token>/` | `login` | Serves the stored image |
| GET | `/exercises/image-highlighted/<token>/` | `token` | Serves the image with the model's highlight boxes drawn on it |

The phone-facing upload routes use token-based access to support a phone
without an existing session. An upload token is random, expires after ten minutes, and
accepts one successful upload. The subsequent guidance request links the
upload to its attempt through the interaction trace. The highlighted-image route
also treats the path token as a bearer credential.

## Quiz routes (student)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/exercises/cohorts/<cohort_id>/quiz/waiting/` | `login` | The waiting room |
| GET | `/exercises/api/quiz/<cohort_id>/overview/` | `login` | Current quiz state |
| POST | `/exercises/api/quiz/<cohort_id>/presence_heartbeat/` | `login` | Refreshes the caller's presence score |

Presence is a Redis sorted set scored by the epoch second of the last heartbeat.
The room count includes heartbeats received within the last thirty seconds.

## Teacher routes

Mounted at `/teachers/`. These render HTML.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/teachers/dashboard/` | `login` | Teacher dashboard |
| GET | `/teachers/courses/<pk>/` | `course:owner,editor,viewer` | Course detail |
| GET, POST | `/teachers/courses/<pk>/edit/` | `course:owner,editor` | Course settings, including the tutor configuration |
| GET, POST | `/teachers/courses/<course_pk>/modules/<module_pk>/add_exercise/` | `login` | Exercise creation form |
| GET, POST | `/teachers/courses/<course_pk>/edit_exercise/<exercise_pk>/` | `login` | Exercise edit form |
| GET | `/teachers/cohorts/<pk>/` | `cohort:owner,teacher` | Cohort detail |
| GET | `/teachers/cohorts/<cohort_id>/students/<student_id>/` | `cohort:owner,teacher` | One student's work |
| GET | `/teachers/cohorts/<cohort_id>/exercises/<exercise_id>/` | `cohort:owner,teacher` | One exercise across the cohort |
| GET | `/teachers/courses/<course_id>/analytics/` | `login` | Course analytics dashboard |
| GET | `/teachers/exercises/<exercise_id>/analytics/` | `login` | Per-exercise analytics |
| GET | `/teachers/exercises/<exercise_id>/annotate/` | `login` | Entry point for annotation |
| GET, POST | `/teachers/exercises/<exercise_id>/annotate/<attempt_id>/` | `login` | Annotates one attempt `good`/`bad`/`unknown` with notes |
| GET | `/teachers/modules/<module_id>/export/` | `login` | Exports a module as JSON |
| POST | `/teachers/courses/<course_id>/import-module/` | `login` | Imports a module from JSON |

Module import validates the whole document and reports every error at once
before writing anything, inside a transaction.

## Teacher JSON APIs

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/teachers/api/reorder_modules/` | `login` | Reorders modules within a course |
| POST | `/teachers/api/reorder_exercises/` | `login` | Reorders exercises within a module |
| POST | `/teachers/api/modules/create/` | `login` | Creates a module |
| POST | `/teachers/api/modules/<module_id>/visibility/` | `login` | Shows or hides a module |
| POST | `/teachers/api/modules/<module_id>/archive/` | `login` | Archives a module |
| POST | `/teachers/api/exercises/<exercise_id>/visibility/` | `login` | Shows or hides an exercise |
| POST | `/teachers/api/exercises/<exercise_id>/duplicate/` | `login` | Duplicates an exercise |
| POST | `/teachers/api/exercises/<exercise_id>/delete/` | `login` | Deletes an exercise |
| GET, POST | `/teachers/api/exercises/<exercise_id>/archive/` | `login` | Reads the attempt count or archives the exercise |
| POST | `/teachers/ai/authoring_assistant/` | `login` | The conversational authoring assistant |
| POST | `/teachers/ai/translate_i18n/` | `login` | Translates exercise fields into the course languages |

### `POST /teachers/ai/authoring_assistant/`

Two modes. `edit` returns a short message and a complete replacement exercise
which the form applies to its fields. `feedback` returns concise suggestions
for improving the exercise.

```json
{ "mode": "edit", "exercise": { "...": "..." }, "messages": [], "context": { "course_pk": 7 } }
```

## Quiz routes (teacher)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/teachers/cohorts/<cohort_id>/quiz/<module_id>/` | `login` | Quiz control interface |
| GET | `/teachers/api/quiz/<cohort_id>/<module_id>/exercises/<exercise_id>/results/` | `login` | Live results for one question |
| POST | `/teachers/api/quiz/<cohort_id>/<module_id>/reset/` | `login` | Resets quiz state |

Driving a cohort requires the teacher lock, taken with a conditional Redis set
and released by a Lua script that deletes the key only if the value still
matches the caller. A teacher whose lock lapses becomes a spectator.

## Authoring assistant routes

Mounted at `/teacher/authoring-assistant/`. Bulk generation of exercises from
uploaded course material.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/teacher/authoring-assistant/` | `login` | Landing page with course selection |
| GET | `/teacher/authoring-assistant/start/?course_id=<id>` | `login` | Starts or resumes a session |
| GET | `/teacher/authoring-assistant/session/<session_id>/` | `login` | Session chat interface |
| POST | `/teacher/authoring-assistant/session/<session_id>/message/` | `login` | Sends a message |
| POST | `/teacher/authoring-assistant/session/<session_id>/upload/` | `login` | Uploads course material |
| POST | `/teacher/authoring-assistant/session/<session_id>/file/<file_id>/delete/` | `login` | Removes an uploaded file |
| POST | `/teacher/authoring-assistant/session/<session_id>/build/` | `login` | Generates exercises from the material |
| GET | `/teacher/authoring-assistant/session/<session_id>/traces/` | `login` | Model traces for the session |
| GET, POST | `/teacher/authoring-assistant/session/<session_id>/review/` | `login` | Reviews exercises or completes the session |
| POST | `/teacher/authoring-assistant/session/<session_id>/abort/` | `login` | Aborts the session and removes its generated module |
| POST | `/teacher/authoring-assistant/exercises/<exercise_id>/approve/` | `login` | Clears the draft marker on a generated exercise |

A partial unique index restricts each teacher to one active session per course.
Generated exercises land in a draft state signaled by the assistant's
commentary, so an unreviewed item is identifiable.

## Evaluation routes

Mounted at `/evaluation/`. The blind model-comparison subsystem.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET, POST | `/evaluation/<experiment_id>/evaluate/` | `login` | Presents responses side by side, unlabeled, and records a ranking |
| GET | `/evaluation/<experiment_id>/stats/` | `login` | Aggregate statistics for the experiment |

Rankings are typed as a string of letters. Parentheses express a tie, so an
evaluator who considers two responses equivalent records the tie and leaves it
unbroken; ranks skip after a tie, so two responses tied first are followed by a
third. An experiment locks after its first comparison, so a configuration
cannot shift underneath a partially collected dataset.

## Mobile routes

Mounted at `/m/`. A companion client reached by magic link.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/m/` | `none` | Mobile dashboard; redirects to login when no session exists |
| GET | `/m/install/` | `login` | PWA install instructions |
| GET | `/m/exercise/<exercise_id>/` | `login` | Mobile exercise view |
| POST | `/m/voice-transcribe/` | `login` | Transcribes recorded audio through a speech model |
| GET | `/m/auth/request-link/` | `none` | Form requesting a magic link |
| POST | `/m/auth/send-link/` | `none` | Mails the link. `csrf_exempt` |

## WebSocket

```
ws://<host>/ws/quiz/<cohort_id>/<module_id>/
```

The Channels middleware exposes the Django session to the consumer. Control
actions are limited to cohort owners and teachers and require the Redis teacher
lock.

Quiz-state reception and presence heartbeats are available to connections
that reach the consumer, including connections without a cohort session.
For private quizzes, configure connection-level access for the intended cohort.
Teacher control actions use the role and lock checks described above.

Use `wss://` when the site is served over HTTPS. This transport carries quiz state to a
cohort in synchrony, backed by three Redis structures: a hash for quiz state
expiring after two hours, a sorted set for presence, and a string for the
teacher lock.

Countdowns carry both a duration and an absolute end time. Clients render from
the end time, so a student who joins late or whose tab was throttled still sees
the correct remaining time, while the server independently schedules the
transition. Display and authority stay separate.

Implemented by `QuizConsumer` in `steacher_app/exercises/consumers.py`.

## Rate limits

Applied by the `rate_limit` decorator in `steacher_app/exercises/authz.py`.
Limits are per minute.

| Route | Per user | Per IP |
|---|---|---|
| `/exercises/api/scala/execute/` | 20 | 80 |
| `/exercises/chat/threads/<id>/send/` | 20 | 50 |
| `/exercises/image/upload-token/` | 5 | — |
| `/exercises/upload/<token>/submit/` | — | 10 |
| `/m/voice-transcribe/` | 20 | — |
| `/m/auth/send-link/` | — | 10 |

The application limiter keeps both user and client-address buckets in the
Django session. A new session starts fresh buckets; limiter errors allow the
request to continue. For limits shared across sessions and workers, configure
additional controls at the reverse proxy.

Nginx separately throttles the web login, admin login, and password-reset
routes by client address; see `nginx/` and [DEPLOY.md](../DEPLOY.md).
