# Real-Time Quiz System Specification

## Overview

The Steacher quiz system is a real-time, teacher-controlled quiz mechanism that enables synchronous assessment of students within a cohort. Built using Django Channels and WebSockets, it provides instant state synchronization between teacher controls and student interfaces, ensuring a smooth and coordinated quiz experience for classes of up to 100+ students.

## Goals

1. **Real-time Synchronization**: Enable instant updates across all participants without polling overhead
2. **Teacher Control**: Ensure single-teacher authority over quiz flow with explicit state transitions
3. **Student Fairness**: Enforce synchronized question timing with automatic submission deadlines
4. **Simplicity**: Minimize database operations and complexity while maintaining reliability
5. **AI Integration**: Leverage existing AI tutor for automatic grading within the quiz context

## Architecture Decision: Redis Over Database

We chose Redis as the primary state store for quiz sessions rather than persisting state in PostgreSQL for several reasons:

- **Ephemeral Nature**: Quiz states are transient and don't require long-term persistence
- **Performance**: Redis provides sub-millisecond latency for state updates critical for real-time interaction
- **Simplicity**: No need for complex database migrations or cleanup jobs for expired sessions
- **Natural TTLs**: Redis key expiration naturally handles abandoned sessions and stale locks
- **WebSocket Integration**: Redis pub/sub seamlessly integrates with Django Channels for broadcasting

The only database persistence occurs via the `QuizLog` model, which records completed quiz sessions for analytics purposes.

## Technical Stack

- **Django Channels**: WebSocket support and ASGI application handling
- **Redis**: State management, presence tracking, and message broadcasting
- **WebSockets**: Bi-directional real-time communication protocol
- **Vue.js 3**: Reactive frontend for teacher control interface

## Workflow

### Teacher Flow

1. **Setup** (`/teachers/cohorts/<id>/`): Teacher selects a quiz module from the cohort page
2. **Control Interface** (`/teachers/cohorts/<id>/quiz/<module_id>/`): 
   - Acquires exclusive control lock (Redis-based, 60s TTL with heartbeat refresh)
   - Initiates "gathering" state to allow students to join
   - Starts quiz, moving to first exercise (state: "display_question")
   - Configures countdown duration per question (default: 5s, minimum: 5s, stored in Redis only)
   - Clicks "Start Countdown" to trigger countdown (broadcasts to all students)
   - Reviews aggregated results after countdown (state: "results_for_current_question")
   - Can jump to any exercise via dropdown navigation
   - Advances through exercises or jumps to specific questions
   - Ends quiz session, logging completion to database

### Student Flow

1. **Discovery**: "Join Quiz" button appears on dashboard and course details page when quiz is in "gathering" or "display_question" state. Page refresh required.
2. **Waiting Room** (`/exercises/cohorts/<cohort_id>/quiz/waiting/`): 
   - WebSocket connection established
   - Real-time presence updates shown
   - Auto-redirects when quiz becomes active (state: "display_question")
3. **Exercise View** (`/exercises/cohorts/<cohort_id>/quiz/exercise/<exercise_id>/`):
   - Standard exercise interface with quiz header overlay
   - Module ID determined from exercise's parent module (no URL parameter needed)
   - Previous/Next navigation buttons disabled during quiz mode
   - Real-time countdown display when teacher triggers it
   - Students can continue working until countdown reaches zero
   - Automatic submission via `window.submitAnswer()` when countdown reaches zero (no warning)
   - Auto-navigation to next question or back to waiting room
   - Students joining mid-quiz are redirected to current question
4. **Results Viewing**: Students view results on teacher's projected screen (no individual results display)
5. **Quiz Completion**: Students auto-redirect to cohort page when teacher ends quiz. No summary screen.

## Key Components

### Backend Components

#### `exercises/consumers.py`
Single `QuizConsumer` class handling both teacher and student connections:
```python
class QuizConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Note: WebSocket connections close on page navigation
        # Each new page = new WebSocket connection = new teacher check
        self.is_teacher = await self.check_is_teacher_once()
        # Join quiz group 'quiz_{cohort_id}_{module_id}'
        # Module ID determined from exercise.module relationship
        # Update presence in Redis
    
    async def receive(self, text_data):
        # Teacher commands: start_gathering, start_quiz, start_countdown, next_question, end_quiz
        # Student updates: presence heartbeat only
        # TODO: Future enhancement - handle teacher control handoff
    
    # Message handlers (called via Django Channels group broadcast)
    async def quiz_state_update(self, event):
        # Sends state change to WebSocket client
        await self.send(text_data=json.dumps(event))
        
    async def countdown_start(self, event):
        # Sends countdown info to WebSocket client
        await self.send(text_data=json.dumps(event))
        
    async def navigate_to(self, event):
        # Sends navigation command to WebSocket client
        await self.send(text_data=json.dumps(event))
```

### Frontend Components

#### `templates/exercises/teacher/quiz_control.html`
Full teacher control interface with:
- Real-time status display
- Student presence counter (live updates)
- Initial state is "not_started". Offers "Start Gathering Students" button.
- Question title and markdown-formatted description (when displaying a question)
- Dropdown to jump to gathering state or any exercise in the module
- Countdown configuration (per-question, 5s minimum)
- "Start Countdown" button (visible only when displaying a question)
- Question correct answer (only when results_for_current_question state)
- Grading progress: "Grading in progress: X of Y completed" while AI processes
- Results display: horizontal bar split between correct (blue) and incorrect (gray)
- End quiz button

#### `templates/exercises/students/quiz_waiting.html`
Student waiting room with:
- Status updates (gathering/display_question/completed)
- Connected student count
- Auto-redirect when quiz becomes active (state: "display_question")

#### `templates/exercises/quiz_header.html`
Overlay component for exercise pages during quiz mode:
- Real-time countdown display (seconds remaining)
- Auto-submission trigger when countdown reaches zero
- Calls `window.submitAnswer()` automatically if it hasn't been called already by student (check `window.hasAlreadySubmittedThisQuestion` flag)
- Quiz status indicators
- Previous/Next navigation buttons disabled

### Redis Data Structure Details

```python
# 1. Quiz State Hash
# Key: quiz:state:{cohort_id}:{module_id}
# Type: Hash
# Fields:
{
    'state': 'display_question',       # Values: gathering|display_question|results_for_current_question|completed
    'current_exercise_id': '42',       # ID of current exercise (null when in gathering state)
    'countdown_duration': '10',        # Teacher-configured duration in seconds (default: 5, min: 5)
    'countdown_end_time': '1699234567', # Unix timestamp when countdown expires (set when countdown active)
    'teacher_id': '123'                # ID of the teacher who started the quiz
}
# TTL: 2 hours (7200 seconds)

# 2. Student Presence Set
# Key: quiz:presence:{cohort_id}
# Type: Set
# Members: User IDs as strings (e.g., "101", "102", "103")
# Each member has individual TTL of 30 seconds (refreshed on heartbeat)
# Example: SADD quiz:presence:5 "101" "102" "103"

# 3. Teacher Control Lock
# Key: quiz:lock:{cohort_id}:{module_id}
# Type: String
# Value: Teacher user ID as string (e.g., "123")
# TTL: 60 seconds (teacher must send heartbeat every 30s to maintain control)
# Example: SET quiz:lock:5:10 "123" EX 60
```

### State Machine

```
not_started → gathering → display_question → results_for_current_question → display_question (next) → ... → completed
                                 ↑                                                 ↓
                                 └─────────────────────────────────────────────────┘
```


State transitions:
- `not_started` → `gathering`: Teacher opens quiz control page and clicks "Start Gathering Students" button
- `gathering` → `display_question`: Teacher clicks "Start Quiz" button (navigates to first exercise)
- `display_question` → `results_for_current_question`: Countdown reaches zero (automatic transition)
- `results_for_current_question` → `display_question`: Teacher clicks "Next Question" button
- Any state → `completed`: Teacher clicks "End Quiz" button

## AI Grading Integration

The system reuses the existing AI tutor infrastructure:
1. Student submissions create standard `Attempt` records (forced submission at countdown zero)
2. AI tutor processes submissions normally, creating `Trace` records
3. Results are already stored in traces - no separate aggregation needed
4. Teacher's browser polls database every 2 seconds for updated results (AJAX, only during results_for_current_question)
5. Display shows "Grading: X of Y completed" until all submissions processed
6. Aggregation query counts traces with `<exercise_completed>` tags for current exercise

## Design Decisions

1. **Single Consumer**: One `QuizConsumer` class for both teachers and students
2. **WebSocket Per Page**: New connection on each page navigation (WebSockets don't survive navigation)
3. **Teacher-Configurable Countdown**: Per-question, minimum 5s, stored in Redis state hash
4. **Simple Result Updates**: Teacher UI polls database via AJAX instead of complex WebSocket push
5. **Projected Results**: Students view results on teacher's projected screen only
6. **Auto-Submit Interface**: Uses existing `window.submitExercise()` function
7. **Direct Completion**: Redirect to cohort page, no summary screen
8. **TTL Cleanup**: Redis handles expired data automatically (no manual cleanup needed)
9. **No Edge Case Handling**: Students who play games with refresh/navigation face consequences
10. **Teacher Lock**: No handoff mechanism for now (TODO comment in code)

## Performance Considerations

- **DB Queries**: Teacher status checked once per WebSocket connection (on each page load)
- **Presence Updates**: Student heartbeats every 20 seconds to maintain presence
- **Result Polling**: Teacher polls for results only when in `results_for_current_question` state (2-second interval)
- **WebSocket Efficiency**: State updates broadcast to all participants instantly via Redis pub/sub
- **URL Parameters**: Module ID passed via URL to maintain context across page navigations

