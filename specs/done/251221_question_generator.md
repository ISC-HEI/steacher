# Question Generator Feature

Add a conversational question generator tool that allows teachers to brainstorm and refine exercise ideas through chat before generating structured exercises. This extends the existing content import system [251220_exercice_creation_wizard.md](251220_exercice_creation_wizard.md) with an interactive discussion phase.

## User Flow

1. Teacher clicks "Exercise Generator" button (replaces the "Import exercises" button)
2. Teacher selects course (mandatory, becomes locked after first message)
3. Teacher optionally uploads reference files (PDFs, code, images, etc.)
4. AI shows welcome message in chat interface: "Hi! I can help you create exercises. What would you like to build?"
5. Teacher chats with AI to brainstorm exercise ideas (clicks on "Send" button)
6. Teacher can add/remove files during conversation (AI auto-acknowledges file uploads)
7. When ready, teacher clicks "Build Exercises" button (disabled until first conversation exchange)
8. System generates exercise plans in background (spinning wheel, all buttons disabled)
9. Two outcomes:
   - **Success**: Redirect to review page with generated exercise candidates
   - **Failure**: Return to chat page with error message from AI, teacher can refine and retry
10. Teacher reviews and validates exercises on existing review page
11. Teacher completes session or aborts (can't exit until complete/aborted)

## Key Features

### 1. File Upload with Persistence

**UI Components:**
- Course selector dropdown (required, existing)
- "Upload Files" button (opens file picker)
- List of uploaded files with delete (X) button next to each
- Confirmation dialog before deleting files

**Backend:**
- Store files locally in `UploadedFile` model (existing)
- Upload files to Gemini File API immediately on upload
- Store Gemini file URI in `UploadedFile.gemini_file_uri` (new field)
- Use Gemini Context Caching to cache file content + system prompt
- When file is deleted: remove from local DB, let Gemini file expire naturally (48h TTL)

**Context Caching Strategy:**
```python
# Cache structure (prefix that stays constant):
cache = client.caches.create(
    model="gemini-2.5-flash",
    config={
        'system_instruction': CHAT_SYSTEM_PROMPT,
        'contents': [
            # Course context
            course_context_text,
            # File URIs (from Gemini File API)
            file_uri_1,
            file_uri_2,
            ...
        ],
        'ttl': '3600s'  # 1 hour
    }
)

# Each chat turn references cache + adds conversation history
response = client.models.generate_content(
    model="gemini-3-pro-preview",
    contents=[
        # Conversation history (Trace records)
        {'role': 'user', 'parts': [...]},
        {'role': 'model', 'parts': [...]},
        # New user message
        {'role': 'user', 'parts': [new_message]}
    ],
    config={'cached_content': cache.name}
)
```

**Cache Creation & Invalidation:**
- **Lazy creation**: Cache created on first message send (not on file upload)
- Cache creation takes ~3-4 seconds (acceptable latency for first message)
- When teacher adds file mid-conversation: invalidate cache, recreate on next message send
- When teacher removes file: invalidate cache, recreate on next message send
- Cache TTL: 1 hour (sufficient for typical session)
- Store current cache name in `AuthoringSession.cache_name` (new field)

### 2. Chat Interface

**UI Components:**
- Course selector dropdown (disabled after first message with tooltip: "Can't change course mid-creation")
- Message list (scrollable, auto-scroll to bottom)
  - Initial AI welcome message: "Hi! I can help you create exercises. What would you like to build?"
  - System messages for file uploads: "I see you uploaded exercises.pdf. Let me review it..."
- Text input area (multiline)
- Two action buttons:
  - "Send" (Enter to send, Shift+Enter for newline)
  - "Build Exercises" (disabled until first conversation exchange, then enabled)
- "Abort Process" button at bottom (same as review page)

**Build Exercises Flow:**
- Click "Build Exercises" → show spinning wheel, disable all buttons
- Display message: "Waiting for exercise plans to be generated.. This can take 30 seconds to a minute..."
- AI generates exercise plans (segmentation phase) in background
- Two outcomes:
  - **Success**: Redirect to review page
  - **Failure**: Stay on chat page, show AI error message in conversation (e.g., "I don't have enough material. Please provide...")

**Message Rendering:**
- User messages: right-aligned, blue background
- AI messages: left-aligned, gray background
- System messages (file uploads): centered, light gray background, italic
- Support Markdown rendering (use Marked + DOMPurify)
- Support LaTeX math rendering (use KaTeX)
- Support code syntax highlighting (use PrismJS)

**Storage:**
- Store conversation in `Trace` model with `channel='question_generator'`
- Link traces to `AuthoringSession` via GenericForeignKey
- Each trace stores one exchange (user message + AI response)
- System messages (file uploads) also stored as traces with special metadata

### 3. Two-Phase Generation

#### Phase 1: Content Organization (Chat → Segmentation)

When teacher clicks "Build Exercises", system:

1. Sends conversation history + build prompt to Gemini
2. AI outputs `SegmentationResult` (same schema as content import):
   ```python
   class SegmentationResult(BaseModel):
       module_name: str
       module_description: str
       message_to_teacher: str
       errors_to_teacher: str
       exercises: List[SegmentedExercise]
   
   class SegmentedExercise(BaseModel):
       title: str
       content: str  # Problem statement
       solution: str  # Expected solution (can be empty)
   ```
3. Store result in `AuthoringSession.segmentation_data`
4. Transition to Phase 2

#### Phase 2: Exercise Building (Parallel)

Same as current content import:

1. Create module from segmentation data
2. For each `SegmentedExercise`, spawn async task
3. Each task calls existing `build_single_exercise_async()` function
4. Exercises created as drafts in review page
5. Teacher validates each exercise

**Key Insight:** We reuse the entire Phase 2 infrastructure. Only Phase 1 changes (chat → segmentation instead of document → segmentation).

## Prompt Structure

### Prompt 1: Question Generator Chat (`question_generator_chat_prompt.md`)

**Purpose:** Collaborative brainstorming and refinement of exercise ideas.

**Key Behaviors:**
- Leverage context to guide the conversation (see "Context Available" section below)
- If not clear or not provided by the teacher, ask clarifying questions about:
  - Learning objectives
  - Difficulty level (beginner/intermediate/advanced)
  - Exercise types (Python, SQL, Scala, Turtle, Open Question)
  - Number of exercises desired
  - Topics to cover
- Suggest exercise ideas with brief descriptions
- Refine ideas based on teacher feedback
- **Proactively signal readiness**: When enough detail is gathered, say something like:
  - "I think we have enough context to build 5 exercises on recursion. Ready when you are!"
  - "Based on our discussion, I can create 3 Python exercises covering loops and conditionals. Should I proceed?"
- On the contrary, if the teacher has not provided enough context, ask for more context:
  - "I don't have enough context to generate exercises. Please provide more information about the course, the learning objectives, the difficulty level, the exercise types, the number of exercises desired, the topics to cover."
- **IMPORTANT**: Ask questions when unclear. Don't make assumptions, ask for clarification. This is the right place to ask for more context. The teacher owes it to the AI to provide enough context to generate exercises.

**Context Available:** (will be provided by the system if available)
- Course description and learning goals
- Course-specific prompt (`Course.course_prompt`) - **IMPORTANT**: If not available, advise teacher to add one for better results
- Existing exercises in course (titles + first 200 chars of question)
- Exercise type schemas (so AI knows what's possible)
- Uploaded files (via Gemini File API + Context Cache)
- Teacher's previous messages

**Special Behaviors:**
- If no files uploaded: Suggest "Consider uploading reference materials for better context, if you have any"
- When file is uploaded mid-conversation: Automatically acknowledge with "I see you uploaded [filename]. Let me review it..."
- If `course_prompt` is missing: Advise teacher to add course context for better exercise generation

**Output Format:** Natural conversational text (Markdown, LaTeX supported)

### Prompt 2: Exercise Builder (`question_generator_build_prompt.md`)

**Purpose:** Extract structured exercise specifications from conversation.

**Input:**
- Last 20 messages from conversation history
- Course context
- Uploaded files (via cache)

**Output Format:** JSON matching `SegmentationResult` schema

**Key Behaviors:**
- Extract number of exercises from conversation (or default to reasonable number)
- Infer exercise types from discussion
- Create clear problem statements
- Extract solutions if discussed
- Generate appropriate module name/description
- **CRITICAL**: If information is insufficient, return error in `errors_to_teacher` field:
  - "I don't have enough material to generate exercises. Please provide more details about [specific missing info]."
  - This allows teacher to refine conversation and retry
- If successful, provide encouraging message in `message_to_teacher`

**Important:** It is NOT the role of this prompt to generate the complete exercises. It is only to extract the structured exercise specifications from the conversation. The complete exercises will be generated individually in the next phase (same as content import).

**Example Transformation:**

Chat excerpt:
```
Teacher: I need 3 Python exercises on recursion for beginners
AI: Great! Should they cover factorial, fibonacci, or other patterns?
Teacher: Let's do factorial, fibonacci, and sum of digits
AI: Perfect. Should they have unit tests?
Teacher: Yes
```

Generated output:
```json
{
  "module_name": "Recursion Basics",
  "module_description": "Introduction to recursive functions in Python",
  "message_to_teacher": "Generated 3 beginner Python exercises on recursion with hints and test cases",
  "errors_to_teacher": "",
  "exercises": [
    {
      "title": "Factorial Function",
      "content": "A Python function that calculates the factorial of a given number.",
      "solution": ""
    },
    // ... 2 more exercises
  ]
}
```

**Important:** the `solution` field is empty because it is not provided in the conversation. In this phase, we do NOT generate the complete exercise. It will be generated in the next phase.

## Database Schema Changes

### `AuthoringSession` Model

Add field:
```python
cache_name = models.CharField(
    max_length=255,
    blank=True,
    help_text="Gemini cache name for context caching"
)
```

Remove field:
```python
# Remove this field - no longer needed since we have full conversation in Traces
teacher_instructions = models.TextField(...)
```

**Note:** There is no difference between question generator sessions and direct import sessions. Everything is handled by the same session model and stored in Traces.

### `Course` Model (in `exercises/models.py`)

Remove field:
```python
# Remove this field - redundant with course_prompt
chat_prompt = models.TextField(...)
```

### `UploadedFile` Model

Add field:
```python
gemini_file_uri = models.CharField(
    max_length=500,
    blank=True,
    help_text="Gemini File API URI for this file (e.g., 'files/abc123')"
)
```

## API Endpoints

### `POST /authoring/chat/` (new)

Send chat message in question generator.

**Request:**
```json
{
  "session_id": 123,
  "message": "I need 5 exercises on Python loops"
}
```

**Response:**
```json
{
  "assistant_message": "Great! What difficulty level...",
  "trace_id": 456
}
```

**Logic:**
1. Get session and validate permissions
2. Lock course selector (session.course can't change after first message)
3. Get or create Gemini cache (lazy creation on first message, ~3-4 seconds)
   - Cache includes: system prompt + course context + file URIs
4. Load conversation history from Traces (all messages)
5. Call Gemini with cached content + history + new message
6. Create Trace record for this exchange
7. Return AI response

### `POST /authoring/upload-file/` (new)

Upload file during question generator session.

**Request:** `multipart/form-data` with file

**Response:**
```json
{
  "file_id": 789,
  "filename": "exercises.pdf",
  "gemini_uri": "files/abc123"
}
```

**Logic:**
1. Validate file (same rules as content import: 50MB total limit)
2. Store in `UploadedFile` model
3. Upload to Gemini File API
4. Store Gemini URI in model
5. Invalidate current cache (will be recreated lazily on next chat message)
6. Create system Trace message: "I see you uploaded [filename]. Let me review it..."
7. Call Gemini to generate acknowledgment response
8. Return file info + AI acknowledgment

### `DELETE /authoring/file/<file_id>/` (new)

Remove file from session.

**Response:**
```json
{
  "success": true
}
```

**Logic:**
1. Delete `UploadedFile` record
2. Invalidate current cache
3. Let Gemini file expire naturally (48h TTL)

### `POST /authoring/build/` (new)

Trigger exercise generation from conversation.

**Request:**
```json
{
  "session_id": 123
}
```

**Response:**
```json
{
  "success": true,
  "message": "Building exercises in background..."
}
```

**Logic:**
1. Load last 20 messages from Traces
2. Call Gemini with build prompt + conversation history + course context
3. Parse `SegmentationResult`
4. Check for errors:
   - If `errors_to_teacher` is not empty: Return error, stay on chat page, show AI message in conversation
   - If successful: Store in `session.segmentation_data`, proceed to Phase 2
5. Spawn background thread for Phase 2 (reuse `build_all_exercises_async`)
6. Redirect to review page

## UI Implementation

### Template: `authoring_tools/chat.html` (rename from `upload.html`)

**Layout:**
```
┌─────────────────────────────────────────┐
│ Exercise Generator                       │
├─────────────────────────────────────────┤
│ Course: [Dropdown ▼] (locked after 1st) │
│         Tooltip: "Can't change course   │
│         mid-creation"                    │
├─────────────────────────────────────────┤
│ Files:                                   │
│ [Upload Files] button                    │
│                                          │
│ 📄 exercises.pdf [X]                     │
│ 📄 solution.py [X]                       │
│ 🖼️ diagram.png [X]                       │
├─────────────────────────────────────────┤
│ Conversation:                            │
│ ┌─────────────────────────────────────┐ │
│ │ [AI welcome message]                │ │
│ │ "Hi! I can help you create..."      │ │
│ │                                     │ │
│ │    [System: File uploaded...]       │ │
│ │                                     │ │
│ │ [AI acknowledgment]                 │ │
│ │                                     │ │
│ │         [User message bubble]       │ │
│ │                                     │ │
│ │ [AI message bubble]                 │ │
│ │                                     │ │
│ └─────────────────────────────────────┘ │
│                                          │
│ [Text input area (multiline)]           │
│ [Send] button                            │
├─────────────────────────────────────────┤
│ [Build Exercises] (disabled until chat) │
│ [Abort Process] (bottom, like review)   │
└─────────────────────────────────────────┘

When "Build Exercises" clicked:
┌─────────────────────────────────────────┐
│ ⏳ Waiting for exercise plans...        │
│ [Spinning wheel]                         │
│ (All buttons disabled)                   │
└─────────────────────────────────────────┘
```

### TypeScript: `frontend/question_generator.ts` (new)

Simple Vue 3 app with:
- Reactive message list
- File upload handling
- Send message function
- Auto-scroll to bottom
- Markdown/LaTeX/code rendering for messages

**No need to reuse `ChatbotPanel.ts`** - build simple, focused UI for this use case.

## Integration Points

### Course Detail Page

Add button next to "Import module":
```html
<button class="button is-primary" @click="openQuestionGenerator">
    <span class="icon"><i class="fas fa-magic"></i></span>
    <span>Exercise Generator</span>
</button>
```

Links to: `/authoring/generator/?course_id=123`

### Review Page

Reuse existing review page. Nees to remove the very first step(s) we used to have on that page, because now it's handled by the chat interface.

## Cost Optimization

**Without Context Caching:**
- 10 conversation turns × 50K tokens (files) = 500K input tokens
- Cost: 500K × $0.10/M = $0.05

**With Context Caching:**
- Initial cache: 50K tokens × $0.10/M = $0.005
- 10 turns: 10 × 50K × $0.025/M = $0.0125
- Total: $0.0175 (65% savings)

**Additional savings:**
- Reduced latency (cached content not reprocessed)
- Files uploaded once, referenced many times
- Cache shared across entire session (1 hour TTL)

## Implementation Checklist

### Backend
- [ ] Add `cache_name` field to `AuthoringSession`
- [ ] Remove `teacher_instructions` field from `AuthoringSession`
- [ ] Remove `chat_prompt` field from `Course` model
- [ ] Add `gemini_file_uri` field to `UploadedFile`
- [ ] Create `question_generator_chat_prompt.md` (with course_prompt advice, file upload suggestion)
- [ ] Create `question_generator_build_prompt.md` (with error handling for insufficient info)
- [ ] Implement Gemini File API upload helper
- [ ] Implement Gemini Context Cache management (lazy creation, ~3-4s latency)
- [ ] Add `POST /authoring/chat/` endpoint (locks course after first message)
- [ ] Add `POST /authoring/upload-file/` endpoint (auto-generates AI acknowledgment)
- [ ] Add `DELETE /authoring/file/<id>/` endpoint
- [ ] Add `POST /authoring/build/` endpoint (last 20 messages, error handling)
- [ ] Rename `upload_documents` view to support chat flow
- [ ] Add session redirection logic (chat vs review based on state)
- [ ] Add URL routing for new endpoints

### Frontend
- [ ] Rename `upload.html` to `chat.html`
- [ ] Redesign template with chat interface
- [ ] Add AI welcome message on page load
- [ ] Add course selector with lock + tooltip after first message
- [ ] Add "Abort Process" button (same as review page)
- [ ] Create `frontend/question_generator.ts`
- [ ] Implement message list rendering (user/AI/system messages)
- [ ] Implement file upload UI with auto-acknowledgment
- [ ] Implement file deletion with confirmation
- [ ] Add Markdown/LaTeX/code rendering
- [ ] Add "Build Exercises" button (disabled until first exchange)
- [ ] Add "Build Exercises" loading state (spinning wheel, disable all)
- [ ] Handle build errors (stay on page, show AI error in chat)
- [ ] Compile TypeScript

### Integration
- [ ] Replace "Import module" with "Exercise Generator" button on course detail page
- [ ] Add session redirection logic (chat vs review based on state)
- [ ] Update URL routing in `authoring_tools/urls.py`
- [ ] Test full flow: chat → build success → review → complete
- [ ] Test build failure flow: chat → build error → refine → retry
- [ ] Test file upload/deletion during conversation (with AI acknowledgment)
- [ ] Test cache invalidation on file changes (lazy recreation)
- [ ] Test course selector lock after first message
- [ ] Test abort process from chat page
- [ ] Test session persistence (close browser, return to same state)
- [ ] Test cost optimization (verify cached tokens in logs, ~3-4s first message)


## Design Decisions

### File Limits
- Maximum 50MB total per session (same as content import)
- No limit on number of files (practical limit from 50MB constraint)

### Conversation Persistence
- Conversation auto-saves via Trace records (channel='question_generator')
- Teacher can close browser and return - conversation history persists
- No explicit "save draft" needed

### Token Usage
- Not shown to teacher (implementation detail)
- Logged for monitoring/debugging

### Message Editing
- Linear conversation only (no editing previous messages)
- Keeps implementation simple and conversation history clear

### Cache Creation Performance
- Cache creation: ~3-4 seconds (based on Gemini API benchmarks)
- Lazy creation strategy: create on first message send (not on file upload)
- Acceptable latency for first message in conversation
- Subsequent messages use cached content (much faster)

### Error Handling
- Gemini API failures during chat: auto-retry once, then show error in chat
- Build phase failures: return to chat page with AI error message, allow refinement
- Teacher can always abort process and start over

### Session Management
- Teacher locked into session until complete/aborted
- Course selection locked after first message
- Automatic redirection to appropriate page (chat or review) based on session state

## Future Enhancements

- [ ] Support for editing/regenerating specific exercises in review phase
- [ ] Conversation templates (e.g., "Create quiz on topic X")
- [ ] Export conversation as markdown
- [ ] Share conversation with other teachers
- [ ] Analytics on conversation patterns (what questions lead to better exercises)
