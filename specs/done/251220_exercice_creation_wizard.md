# Content Import Feature: Bulk Exercise Creation from Documents

Until now, Steacher allows creating individual exercises. But most of the time, teachers will come with a set of existing exercises that need to be added into Steacher. The features below allow for much faster ingestion of exercises.

## Overview

Teachers can upload documents (PDF, TXT, MD, CSV, JSON, TEX, images with OCR) to bulk-create exercises using Gemini 3 Pro. The workflow is fully automated:

1.  **Phase 1 (Analysis)**: AI segments documents into exercises and extracts content/solutions (structured JSON).
2.  **Phase 2 (Generation)**: For each segmented exercise, the system automatically builds a fully formatted exercise (with tests, hints, translations) in parallel.

## Two-Page Flow

1.  **Upload Page** (`/teacher/authoring-assistant/`) - Select course, upload files, provide instructions. Clicking "Analyze Documents" immediately triggers the background pipeline and redirects to Review.
2.  **Review Page** (`/teacher/authoring-assistant/<session_id>/review/`) - Real-time view of the generation process. Teachers review, validate, and edit exercises here.

*Note: The intermediate "Analysis/Chat" page has been removed to streamline the process.*

## Key Design Decisions

-   **New Django app**: `authoring_tools` (keeps exercises app clean)
-   **Templates**: `authoring_tools/templates/` (extends `exercises/base.html`)
-   **Trace channel**: `content_import` linked to `AuthoringSession` via GenericForeignKey
-   **Session constraint**: One active session per teacher/course
-   **Automated Pipeline**: Analysis and Generation run sequentially in a background thread
-   **Structured output**: All LLM calls use strict Pydantic schemas via Gemini's `response_json_schema`
-   **File handling**: Binary files sent directly to Gemini (preserves formatting, images, tables)
-   **File storage**: Binary blobs in `UploadedFile` model
-   **File limits**: Max 50 pages total (PDFs only), 50MB total
-   **Supported formats**: PDF, TXT, MD, CSV, JSON, TEX, images (PNG, JPEG, WEBP, HEIC, HEIF)
-   **Session completion**: Manual via "Complete Session" button, available only when all exercises are validated
-   **Draft state**: Uses `draft_notes` field presence as state flag (non-empty = needs review, empty = ready)
-   **Visibility**: Imported exercises start with `visible=False` for safety
-   **Language**: AI speaks teacher's `preferred_language`, content extracted in original language
-   **Frontend**: Vue.js application for Review page (`frontend/authoring_review.ts`)
-   **LLM Client**: Pure Gemini API (no OpenAI compatibility layer) with strict schema enforcement

## Database Changes

### Exercise Model (`exercises/models.py`)

Add one field:
-   `draft_notes` (TextField, blank=True): AI-generated notes for teacher (plain text).
    -   **Used as State Flag**: If non-empty, the exercise is considered "Draft/Needs Review". If empty, it is considered "Ready".
    -   Special value `"Generating content..."` indicates "Processing" state during background generation.

*Note: The `is_draft` boolean field was removed (migration `0042_remove_exercise_is_draft`) in favor of using `draft_notes` presence as the source of truth.*

### New Models (`authoring_tools/models.py`)

**AuthoringSession**:
-   Links to Course (required) and Module (null until created during Phase 2)
-   Stores teacher instructions and status (analyzing/building/active/completed)
-   Stores segmentation JSON in `segmentation_data` (JSONField)
-   Has GenericRelation to Trace for conversation history
-   Unique constraint: one active session per teacher/course

**UploadedFile**:
-   Stores binary file data with metadata
-   Extracts page count for PDFs only
-   Links to AuthoringSession

## Page 1: Upload

**URL**: `/teacher/authoring-assistant/`

**Form fields**:
-   Course dropdown (filtered by teacher permissions)
-   File upload (multiple, validated on backend)
-   Teacher instructions textarea (optional, with explicit help text)

**Backend validation**:
-   Max 50MB total size
-   Max 50 pages total (PDFs only)
-   Supported formats: PDF, TXT, MD, CSV, JSON, TEX, images (PNG, JPEG, WEBP, HEIC, HEIF)
-   Note: CSV, JSON, TEX are sent as text/plain to Gemini

**Flow**:
-   Check permissions
-   Check for existing active session → auto-archive it (set to `completed`)
-   Create AuthoringSession + UploadedFile records
-   Trigger background thread (`run_full_import_pipeline`)
-   Redirect to review page

## Pipeline Implementation (`authoring_tools/ai_logic.py`)

The pipeline runs in a background daemon thread and orchestrates two phases:

### Phase 1: Segmentation (Sync)
**Goal**: Segment exercises, extract content, return structured JSON

**Gemini call**:
-   Model: `gemini-3-pro-preview`
-   Binary files sent as `Part.from_bytes()` (preserves formatting)
-   Structured output with Pydantic schema: `SegmentationResult`
-   Returns: `module_name`, `module_description`, `message_to_teacher`, list of `exercises` (each with `title`, `content`, `solution`)
-   Result stored in `session.segmentation_data`
-   Trace created for debugging/audit

### Phase 2: Generation (Async)
**Goal**: Convert segmented content into full Steacher exercises

**Flow**:
1.  Create Module from segmentation JSON
2.  Update session status to `'building'`
3.  For each exercise in parallel (using `asyncio.gather()`):
    -   Create minimal Exercise record:
        -   `title_i18n={'en': title}`, `question_i18n={'en': content}`
        -   `visible=False` (safety default)
        -   `draft_notes="Generating content..."` (sets Processing state)
    -   Call async authoring assistant (Gemini 3 Pro)
    -   Assistant detects type, generates tests/hints, translates to fr/de
    -   Updates exercise with full content and sets `draft_notes` to AI feedback
4.  Update session status to `'active'` (ready for review)

**Concurrency**: All exercises processed in parallel via `asyncio.gather()` in a dedicated event loop

**Logging**: Explicit `sys.stdout` handler with `[AI_LOGIC]` prefix for visibility

## Page 2: Review (Vue.js App)

**URL**: `/teacher/authoring-assistant/<session_id>/review/`

**Frontend**: Vue.js SPA (`frontend/authoring_review.ts`) with custom delimiters `[[ ]]`

**Features**:
-   **Polling**: Auto-refreshes every 3s to show progress
-   **Status Display**:
    -   **Processing**: `draft_notes="Generating content..."` - spinner badge, actions disabled
    -   **Draft**: `draft_notes` non-empty - yellow "Draft" badge
    -   **Ready**: `draft_notes` empty - green "Ready" badge
-   **Validation Workflow**:
    -   **Edit**: Opens exercise editor in new tab. Enabled only for Draft exercises. NOTE: Clicking "Edit" automatically marks the exercise as "Ready" (validated) on the assumption that the teacher will review/fix it in the editor.
    -   **Mark as Ready**: Clears `draft_notes` via POST to `/teacher/authoring-assistant/exercises/<id>/approve/`
    -   **Complete Session**: Enabled only when ALL exercises are Ready. Sets session to `completed`.

## Schemas and Type Safety

All LLM interactions use strict Pydantic schemas enforced via Gemini's `response_json_schema`:

**Core Schemas** (`exercises/schemas.py`):
-   `ExerciseData`: Frontend-visible data (answer_template, db)
-   `AnswerData`: Backend-only data (hints, unit_tests, correct_answers, additional_context)
-   `UnitTests`: Nested structure (setup_code, test_cases, timeout_seconds)
-   `TestCase`: Individual test (description, test_code, expected_output)
-   `CompleteExercise`: Full exercise structure with all i18n fields
-   `AuthoringAssistantResponse`: Wrapper for assistant responses (assistant_message + updated_exercise)

**Schema Enforcement**:
-   Segmentation: `SegmentationResult` schema
-   Exercise generation: `AuthoringAssistantResponse` schema
-   Translation: Prompt-based (no strict schema, but validated output)

**Benefits**:
-   Type-safe responses from Gemini
-   No manual JSON parsing needed
-   Validation errors caught at API level
-   Consistent structure across sync/async paths

## Integration

**App structure**:
```
authoring_tools/
├── __init__.py
├── models.py
├── admin.py
├── views.py
├── urls.py
├── ai_logic.py (pipeline + async authoring assistant)
├── content_import_prompt.md
└── templates/
    ├── upload.html
    └── review.html
```

**URLs**:
-   `/teacher/authoring-assistant/` → upload
-   `/teacher/authoring-assistant/<id>/review/` → review
-   `/teacher/authoring-assistant/exercises/<id>/approve/` → API for validation

**Navbar**: "Import Exercises" link (visible to course owners/editors)

## Future Enhancements

-   Session cleanup: Auto-expire after 24 hours
-   Batch operations: Approve/delete multiple exercises
-   Session history: List past sessions
-   Analytics: Track import success rates
-   Support QTI format (Question & Test Interoperability)
-   Retry failed exercises individually
