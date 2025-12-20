# Content Import Feature: Bulk Exercise Creation from Documents

Until now, Steacher allows creating individual exercises. But most of the time, teachers will come with a set of existing exercises that need to be added into Steacher. The features below allow for much faster ingestion of exercises.

## Overview

Teachers can upload documents (PDF, TXT, MD, CSV, JSON, TEX, images with OCR) to bulk-create exercises using Gemini 3 Pro. The workflow has two phases:

**Phase 1 (Segmentation)**: AI segments documents into exercises, extracts content and solutions, returns structured JSON
**Phase 2 (Building)**: For each segmented exercise, call existing authoring assistant to create properly formatted exercises with tests, hints, etc.

## Three-Page Flow

1. **Upload Page** (`/teacher/authoring-assistant/`) - Select course, upload files, provide instructions
2. **Analysis Page** (`/teacher/authoring-assistant/<session_id>/analysis/`) - AI segmentation with structured JSON output
3. **Review Page** (`/teacher/authoring-assistant/<session_id>/review/`) - Exercise list with auto-refresh

## Key Design Decisions

- **New Django app**: `authoring_tools` (keeps exercises app clean)
- **Templates**: `authoring_tools/templates/` (extends `exercises/base.html`)
- **Trace channel**: `content_import` linked to `AuthoringSession` via GenericForeignKey
- **Session constraint**: One active session per teacher/course
- **Two-phase workflow**: Segmentation (Phase 1) → Building (Phase 2)
- **Structured output**: Gemini returns JSON with module info and exercise list
- **File handling**: Upload binary files directly to Gemini File API (preserves formatting, images, tables)
- **File storage**: Binary blobs in `UploadedFile` model
- **File limits**: Max 50 pages total (PDFs only), 50MB total
- **Supported formats**: PDF, TXT, MD, CSV, JSON, TEX, images (PNG, JPEG, WEBP, HEIC, HEIF)
- **Session completion**: Manual via "Complete Session" button
- **Draft visibility**: Hidden from students until published
- **Language**: Chatbot speaks teacher's `preferred_language`, content stays in original language
- **Translation enhancement**: Support non-English source languages in i18n translation
- **Frontend approach**: Minimal inline HTML/JS (no separate TypeScript components)
- **Draft notes display**: Show as first message in exercise editor assistant panel with light blue background

## Database Changes

### Exercise Model (`exercises/models.py`)

Add two fields:
- `is_draft` (BooleanField): Marks exercises as drafts (hidden from students)
- `draft_notes` (TextField): AI-generated notes for teacher (plain text, not JSON)

### New Models (`authoring_tools/models.py`)

**AuthoringSession**:
- Links to Course (required) and Module (null until created during Phase 1)
- Stores teacher instructions and status (analyzing/active/building/completed)
- Stores latest segmentation JSON in `segmentation_data` (JSONField)
- Has GenericRelation to Trace for conversation history
- Unique constraint: one active session per teacher/course

**UploadedFile**:
- Stores binary file data with metadata
- Extracts page count for PDFs only
- Links to AuthoringSession

## Page 1: Upload

**URL**: `/teacher/authoring-assistant/`

**Form fields**:
- Course dropdown (filtered by teacher permissions)
- File upload (multiple, validated on backend)
- Teacher instructions textarea (optional, with explicit help text)

**Backend validation**:
- Max 50MB total size
- Max 50 pages total (PDFs only)
- Supported formats: PDF, TXT, MD, CSV, JSON, TEX, images (PNG, JPEG, WEBP, HEIC, HEIF)
- Note: CSV, JSON, TEX are sent as text/plain to Gemini

**Flow**:
- Check permissions
- Check for existing active session → auto-complete it, redirect to analysis page
- Create AuthoringSession + UploadedFile records
- Redirect to analysis page

## Page 2: Analysis (Phase 1: Segmentation)

**URL**: `/teacher/authoring-assistant/<session_id>/analysis/`

**Components**:
- File summary table
- Chatbot interface (inline HTML/JS)
- "Create Exercises" button (triggers Phase 2)

### Phase 1: Segmentation Workflow

**Goal**: Segment exercises, extract content, return structured JSON

**Gemini call with structured output**:
1. Upload files to Gemini File API (binary, preserves formatting/images)
2. Send prompt with JSON schema
3. Gemini returns structured JSON:

```json
{
  "module_name": "Recursion Exercises",
  "module_description": "Practice problems for recursive algorithms",
  "message_to_teacher": "I analyzed your midterm exam PDF. The exercises are well-structured. Some exercises include handwritten solutions extracted via OCR.",
  "exercises": [
    {
      "title": "Fibonacci Sequence",
      "content": "Write a function fib(n) that returns the nth Fibonacci number...",
      "solution": "def fib(n):\n    if n <= 1: return n\n    return fib(n-1) + fib(n-2)"
    },
    {
      "title": "Binary Search",
      "content": "Implement binary search on a sorted array...",
      "solution": ""
    }
  ]
}
```

**JSON Schema** (Pydantic):
```python
class SegmentedExercise(BaseModel):
    title: str
    content: str  # Problem statement
    solution: str  # Can be empty if not in document

class SegmentationResult(BaseModel):
    module_name: str
    module_description: str
    message_to_teacher: str  # High-level observations only
    exercises: List[SegmentedExercise]
```

**UI Rendering**:
- Display `message_to_teacher` from Gemini
- Programmatically generate exercise list from JSON:
  - ✓ Exercise 1: Fibonacci Sequence (has solution)
  - ✓ Exercise 2: Binary Search (⚠️ no solution provided)

**Teacher interaction**:
- Can chat to modify: "Rename exercise 2 to 'Advanced Binary Search'"
- Gemini returns updated JSON with changes
- Teacher clicks "Create Exercises" when satisfied

**Prompt**: `authoring_tools/content_import_prompt.md`
- Speaks teacher's `preferred_language`
- Includes `course.course_prompt` for context
- Focus: Segmentation and extraction only, minimal thinking
- Returns structured JSON

### Phase 2: Building Exercises

**Triggered by**: Teacher clicks "Create Exercises" button

**Implementation**: Async Django view with parallel Gemini API calls. Note: Django Channels was used in the past, but was removed in favor of pure async Django views for simplicity and not to add a background worker.

**Flow**:
1. Teacher clicks "Create Exercises"
2. Async view starts processing in background (fire-and-forget)
3. Teacher immediately redirected to review page
4. Async view processing:
   - Creates Module from JSON (`module_name`, `module_description`)
   - Updates session status to 'building'
   - For each exercise in JSON (in parallel using `asyncio.gather()`):
     - Create minimal draft Exercise (title, question from `content`)
     - Call async authoring assistant: "Create a [type] exercise from this: [content]. Expected solution: [solution]"
     - Authoring assistant detects type, generates tests, formats properly, updates exercise
     - Sets `draft_notes` with authoring assistant output
   - Updates session status to 'active' when complete

**Concurrency**: All 5-10 exercises are processed in parallel using `asyncio.gather()`, reducing total time from ~5 minutes (sequential) to ~30 seconds (parallel)

**Progress tracking**: 
- Review page auto-refresh (every 5 seconds) shows exercises as they're created
- Teacher can navigate away and come back later

**Error handling**: `asyncio.gather(return_exceptions=True)` ensures one failed exercise doesn't block others. Errors logged in `draft_notes`.

## Page 3: Review

**URL**: `/teacher/authoring-assistant/<session_id>/review/`

**Features**:
- Auto-refresh every 5 seconds (shows exercises as they're created in Phase 2)
- Toggle switch (bulma-switch-control) to pause/resume refresh
- Table listing exercises from session's module only
- Shows: order, title, type, draft status badge
- "Edit" button opens exercise editor in new tab
- "Complete Session" button sets status to completed

**Frontend**: Inline JavaScript
- Fetch exercises via AJAX
- Update table innerHTML
- Toggle switch event listener

## Exercise Editor Integration

**Draft notes display** (`templates/exercises/teacher/exercise_form.html`):
- When exercise has `draft_notes`, inject as first message in AI Assistant panel
- Styling: Light blue background with "🤖 Import Notes" label
- Format: Plain text in `<pre>` tag
- Logic: Check `exercise.draft_notes` on mount, prepend to messages array

**Implementation**:
- Modify `frontend/exercise_form.ts` to check for draft_notes on mount
- Add to messages array with `mode: 'draft_notes'`
- CSS: `.draft-notes-message` class with light blue background

## AI Logic

### Phase 1: Segmentation (`authoring_tools/ai_logic.py`)

**File handling**:
- Upload binary files directly to Gemini File API using `client.files.upload()`
- No text extraction needed - Gemini handles parsing natively
- Preserves formatting, images, tables

**Gemini call**:
- Model: `gemini-3-pro-preview`
- Structured output with Pydantic schema
- Config: `response_mime_type='application/json'`, `response_json_schema=SegmentationResult.model_json_schema()`
- Includes `course.course_prompt` for context

**Conversation flow**:
- First call: Returns JSON with segmented exercises
- JSON stored in `session.segmentation_data` and `Trace.assistant_metadata`
- Teacher can chat to modify: "Rename exercise 2 to X"
- Subsequent calls: Send full conversation history + files again (Gemini decides if re-read needed)
- Return updated JSON
- All responses stored as Trace records

### Phase 2: Building (`authoring_tools/ai_logic.py`)

**Async function for each segmented exercise**:
1. Create minimal draft Exercise (synchronously with `draft_notes="Generating content..."`):
   - `title_i18n={'en': exercise.title}`
   - `question_i18n={'en': exercise.content}`
   - `exercise_type='open_question'` (default)
   - `is_draft=True`

2. Call async authoring assistant (new async version of `generate_authoring_update`):
   - Uses `client.aio.models.generate_content()` for async Gemini calls
   - Pass structured request: "Create a [type] exercise from this content. Expected solution: [solution]"
   - Detects proper exercise type
   - Generates unit tests, hints, proper formatting
   - Updates exercise with `draft_notes`
   - **Protection**: Critical fields (`id`, `order`, `module`) are protected from AI updates to prevent DB integrity errors

**Concurrency**: 
- All 5-10 exercises are processed in parallel using `asyncio.gather()`.
- Executed in a dedicated **daemon thread** with a new `asyncio.new_event_loop()` to prevent task cancellation when the Django view returns.
- Uses `select_related('course')` and `@sync_to_async` to ensure thread-safe database access and avoid `SynchronousOnlyOperation` errors.

**Progress tracking**: 
- UI polls for exercise list.
- Minimal exercises show "Processing..." badge (blue).
- Finished exercises show "DRAFT" badge (yellow).
- "Building..." banner hides automatically when all processing is complete.

**Logging**: Dedicated logger configuration ensures background thread logs are visible in console.

## Translation Enhancement

**Current limitation**: Frontend hardcodes `source_lang='en'`

**Enhancement**:
- Detect source language in `frontend/exercise_form.ts`: find first non-empty i18n field
- Pass detected `source_lang` to backend
- Backend already supports any source language
- Result: Can translate French → German/English, or German → French/English

## Integration

**App structure**:
```
authoring_tools/
├── __init__.py
├── models.py
├── admin.py
├── views.py (includes async view for Phase 2)
├── urls.py
├── forms.py
├── ai_logic.py (includes async authoring assistant)
├── content_import_prompt.md
└── templates/
    ├── upload.html
    ├── analysis.html
    └── review.html
```

**URLs**: 
- `/teacher/authoring-assistant/` → upload
- `/teacher/authoring-assistant/<id>/analysis/` → analysis
- `/teacher/authoring-assistant/<id>/review/` → review

**Settings**: Add `'authoring_tools'` to `INSTALLED_APPS`

**Navbar**: "Import Exercises" link (visible to course owners/editors and cohort owners/teachers)

**Permissions**: All views check `assert_can_edit_course()`

**Admin**: Register `AuthoringSession` and `UploadedFile` in `authoring_tools/admin.py`

**Cleanup**: Remove `authoring_tools` Channels infrastructure:
- Delete `authoring_tools/consumers.py` and `authoring_tools/routing.py`
- Remove `exercise_builder` channel from `exam_project/asgi.py`
- Remove worker service from `docker-compose.yml`
- Keep Channels/Redis for quiz WebSocket functionality

## Dependencies

**Python**:
- `pypdf>=4.0.0` (PDF page count extraction only)
- Existing `google-genai` SDK with async support (`client.aio.models.generate_content`)

**Frontend**:
- `bulma-switch-control` via CDN in `base.html`

**No new TypeScript files** - all frontend logic inline in templates

**Server**: Requires ASGI server (Daphne or Uvicorn) for async view support - already configured for WebSocket support


## Implementation Notes

**message_to_teacher examples** (high-level observations only):
- "I analyzed 2 PDF files. The documents are well-formatted and text extraction was successful."
- "I found exercises from pages 3-8. Note: Page 5 had poor image quality, some text may be incomplete."
- "The document includes both questions and answer keys. All content has been extracted."

**NOT in message_to_teacher**:
- Exercise count (shown from JSON)
- Which exercises have solutions (shown from JSON)
- Individual exercise details (Phase 2 handles that)

## Future Enhancements

- Session cleanup: Auto-expire after 24 hours
- Batch operations: Approve/delete multiple exercises
- Session history: List past sessions
- Analytics: Track import success rates
- Support QTI format (Question & Test Interoperability)
