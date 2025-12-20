# Module Import/Export Feature

## Overview
This feature allows teachers to export and import course modules (with all their exercises) as JSON files. This enables:
- Backup and migration of course content
- Sharing modules between courses or Steacher instances
- Reuse of course materials across different teaching contexts

## User Interface

### Export
- **Location**: Teacher course details page (`/teachers/courses/<id>/`)
- **Button**: Download icon (⬇) in each module card header
- **Action**: Downloads a JSON file named `{module_name}_export.json`

### Import
- **Location**: Teacher course details page, top-level button next to "Add module"
- **Button**: "Import module" with upload icon (⬆)
- **Action**: Opens modal to upload JSON file
- **Validation**: Checks asset references and schema before import
- **Result**: Creates new module with all exercises (order auto-assigned)

## File Format

### Export JSON Structure
```json
{
  "export_version": "1.0",
  "exported_at": "2025-12-05T10:30:00Z",
  "source_course": {
    "id": 123,
    "name": "Introduction to Python"
  },
  "module": {
    "name": "Module Name",
    "description": "Module description",
    "order": 1,
    "visible": true,
    "is_quiz": false,
    "exercises": [
      {
        "title_i18n": {"en": "...", "fr": "...", "de": "..."},
        "description_i18n": {"en": "...", "fr": "...", "de": "..."},
        "question_i18n": {"en": "...", "fr": "...", "de": "..."},
        "exercise_type": "python",
        "order": 0,
        "exercise_data": {...},
        "answer_data": {...},
        "visible": true,
        "allow_image_upload": false
      }
    ]
  },
  "asset_references": ["shop.sql", "library.sql"]
}
```

## Technical Implementation

### Backend Components

#### Serializers (`exercises/serializers.py`)
- `ExerciseExportSerializer`: Serializes exercise with all fields needed for import
- `ModuleExportSerializer`: Serializes module with nested exercises

#### Views (`exercises/views_teachers.py`)
- `export_module(request, module_id)`: 
  - Authorization: Teacher must have edit permissions on course
  - Returns JSON download with module + exercises + asset references
  
- `import_module(request, course_id)`:
  - Authorization: Teacher must have edit permissions on target course
  - Validation phases:
    1. JSON structure validation
    2. Asset reference validation (checks all referenced assets exist in target course)
    3. Pydantic schema validation (exercise_data, answer_data)
  - Transaction: All creates happen atomically (all-or-nothing)
  - Order handling: Module order auto-assigned (uses existing Module.save() logic)

#### URL Routes (`exercises/urls.py`)
- `GET /teachers/modules/<int:module_id>/export/` → `export_module`
- `POST /teachers/courses/<int:course_id>/import-module/` → `import_module`

### Frontend Components

#### Template (`templates/exercises/teacher/teachers_course_details.html`)
- Export button in module card header
- Import button in top-level toolbar
- Import modal with file upload, validation feedback, loading state

#### TypeScript (`frontend/teacher_course_details.ts`)
- Vue reactive state for modal visibility and import state
- `handleFileSelect()`: Handles file input change
- `submitImport()`: Uploads file via FormData, shows errors/success
- `setShowImportModal()`: Opens/closes modal with state reset

## Validation & Error Handling

### Validation Phases (Fast-Fail)
1. **JSON Structure**: Checks for required fields, version compatibility
2. **Asset References**: Validates all referenced SQL databases/assets exist in target course
3. **Schema Validation**: Pydantic validates exercise_data and answer_data

### Transaction Safety
- All database writes happen inside `transaction.atomic()`
- Any error triggers automatic rollback
- No partial imports possible
- Database state unchanged on failure

### Error Messages
- Missing assets: Lists all missing asset names
- Schema errors: Indicates which exercise/field failed
- Clear user-facing messages in modal notification

## Asset Handling
- Assets are **referenced by name**, not embedded
- SQL database names extracted from `exercise_data.db` field
- Import validation ensures assets exist before proceeding
- Teachers must manually upload assets if missing

## Order Management
- Module order: Auto-assigned as `max(order) + 1` in target course
- Exercise order: Preserved from export (relative ordering maintained)
- Uses existing `Module.save()` logic with race condition handling

## Usage Examples

### Scenario 1: Backup a module
1. Teacher exports "Week 1: Python Basics" from Course A
2. Downloads `Week_1_Python_Basics_export.json`
3. Stores file for safekeeping

### Scenario 2: Share module between courses
1. Teacher exports module from "Python 101" course
2. Opens "Advanced Python" course
3. Clicks "Import module", uploads JSON
4. System validates assets (e.g., SQL databases)
5. If assets missing: Error with list of missing assets
6. If valid: Module created with all exercises

### Scenario 3: Migrate between instances
1. Export module from development instance
2. Upload to production instance
3. Ensure referenced assets uploaded first
4. Import succeeds with proper validation

## Limitations & Considerations

### What's Included
- ✅ Module metadata (name, description, visibility, quiz flag)
- ✅ All exercises (with full i18n data)
- ✅ Exercise types and settings
- ✅ Answer data (hints, test cases, correct answers)
- ✅ Asset references

### What's NOT Included
- ❌ Student data (attempts, traces, evaluations)
- ❌ Course-level settings (prompts, LLM config)
- ❌ Binary assets themselves (SQL databases, images)
- ❌ Cohort data
- ❌ Course memberships

### Design Decisions
- **Module-level scope**: More granular than course-level, easier to share specific units
- **Asset references**: Avoids JSON bloat, encourages proper asset management
- **JSON format**: Better Django integration than YAML, no extra dependencies
- **Atomic transactions**: Ensures data consistency, no orphaned records
