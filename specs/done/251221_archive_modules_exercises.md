# Archive Modules and Exercises Feature

## Overview

Teachers can soft-delete (archive) modules and exercises with a simple delete button. Archived items are hidden from both students and teachers but remain in the database to preserve student work. Only administrators can restore archived items via Django admin.

## Problem

Currently, deleting modules or exercises would use Django's `on_delete=CASCADE`, which would permanently delete all student attempts and work. This is unacceptable - student work is sacred and must be preserved.

## Solution

Add an `archived` boolean field to both Module and Exercise models. Archiving soft-deletes items by hiding them from all views while preserving all data in the database.

## Key Design Decisions

- **Student work is sacred**: Never delete attempts or traces from the database
- **Simple visibility logic**: Students only check `visible=True` (one field, one query)
- **Auto-enforcement**: Archiving automatically sets `visible=False`
- **Cascading archive**: Archiving a module also archives all its exercises
- **No restoration UI**: Only Django admin can restore archived items
- **Simple confirmation**: JavaScript alert (not modal) with clear warning text
- **Hidden everywhere**: Archived items don't appear in course details, analytics, or annotation views

## Database Changes

- Module Model (`exercises/models.py`)
    - Add field `archived`
    - Add constraint `module_archived_must_be_invisible`
    - Override `save()` to set `visible=False` if `archived=True`
- Exercise Model (`exercises/models.py`)
    - Add field `archived`
    - Add constraint `exercise_archived_must_be_invisible`
    - Override `save()` to set `visible=False` if `archived=True`

## Visibility Rules

### Students
- See exercise if: `exercise.visible=True` (that's it!)
- Archiving automatically sets `visible=False`, so archived items are hidden
- No additional queries needed

### Teachers
- Course details page: Filter `module.archived=False` and `exercise.archived=False`
- Analytics views: Filter `archived=False`
- Annotation views: Filter `archived=False`
- Everywhere: Use explicit `.filter(archived=False)` (no helper function needed)

## Backend Implementation

- New View (`exercises/views_teachers.py`)
    - `archive_module(request, module_id)`: Archive a module and all its exercises
    - `archive_exercise(request, exercise_id)`: Archive a single exercise


## Future Enhancements (TODOs)

- [ ] Enhanced warning dialog showing:
  - Count of exercises that will be archived (for modules)
  - Count of student attempts that will become inaccessible
- [ ] "Show archived" toggle in course details page for teachers
- [ ] Bulk archive operations (select multiple exercises)
- [ ] Archive date timestamp field
- [ ] Auto-archive old modules after X months of inactivity
- [ ] Restoration UI for course owners (not just admin)
