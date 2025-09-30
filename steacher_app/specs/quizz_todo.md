I'll review all the changed files in your commit to check for bugs against the quiz specification. Let me start by reading the key files systematically.

[8 tools called]

Let me continue reviewing the views and templates:

[29 tools called]

Now let me compile my findings by checking a few more critical pieces:

[3 tools called]

Based on my comprehensive review of your quiz system implementation, I've found several bugs that need to be addressed:

## Critical Bugs


### 2. **Bug in `quiz_control.ts` `jumpTo()` method**
**Location:** `frontend/quiz_control.ts` (lines 133-140)

```typescript
jumpTo() {
    const sel = (this as any).selectedExerciseId;
    console.log('[quiz_control] jumpTo click', { selected: sel });
    if (sel === 'gathering') {
        this.startGathering();
    } else {
        this.nextQuestion();  // ❌ BUG: Always advances to next in sequence
    }
}
```

When jumping to a specific exercise, it calls `this.nextQuestion()` which will always advance to the next exercise in sequence rather than jumping to the selected exercise ID.

**Fix:** Should be:
```typescript
} else {
    const exId = parseInt(sel);
    if (!Number.isNaN(exId)) {
        this.send('next_question', { exercise_id: exId });
    }
}
```

### 3. **Wrong redirect URL for students when quiz completes**
**Location:** `templates/exercises/quiz_header.html` (line 115) and `templates/exercises/students/quiz_waiting.html` (line 116)

Both redirect students to `/teachers/cohorts/${cohortId}/` when quiz is completed, but students don't have access to teacher URLs. According to the spec (line 67): "Students auto-redirect to cohort page when teacher ends quiz."

**Fix:** Should redirect to a student-accessible URL, probably the dashboard or course page.



## Minor Issues


### 6. **Potential race condition in countdown auto-transition**
**Location:** `exercises/consumers.py` (line 316)

```python
asyncio.create_task(self._auto_finish_countdown(duration))
```

If the teacher triggers multiple countdowns rapidly or the WebSocket reconnects, multiple countdown tasks could be spawned. Consider storing the task and cancelling previous ones.

### 7. **No error handling for missing module_id in quiz_waiting.html**
**Location:** `templates/exercises/students/quiz_waiting.html` (lines 92, 135-147)

If the bootstrap fetch returns no `module_id`, the WebSocket connection will try to connect with `null`, causing issues. The code does check for it (line 137-146), but the error handling just logs and sets `connecting=false` without showing a user-friendly message.

### 8. **Mixed use of exercise sequence in `quiz_control.ts`**
**Location:** `frontend/quiz_control.ts` (line 105)

```typescript
if (exIdStr === 'gathering' || !exIdStr) {
    exIdStr = config.exercises[0] ? String(config.exercises[0].id) : '';
}
```

This assumes the first exercise in the array is the first exercise to show, but if `selectedExerciseId` is not set, it might be better to explicitly require the teacher to select an exercise.

### 9. **No validation that exercise belongs to module in quiz flow**
**Location:** `exercises/consumers.py` (line 298)

When teacher sends `start_quiz` or `next_question` with an exercise_id, there's no validation that the exercise actually belongs to the module being quizzed.

## Summary

**Must fix immediately:**
1. Implement `window.submitAnswer()` functions
2. Fix `jumpTo()` logic in quiz_control.ts
3. Fix redirect URLs for students
4. Standardize Redis configuration

**Should fix before production:**
5-9: Minor issues listed above







## 📊 Current State Analysis

### ✅ What IS Working

1. **Quiz Discovery (Dashboard/Course Details)**
   - Students see "Join Quiz" button when quiz is in `gathering` or `display_question` state
   - Uses `find_active_quiz_for_user()` and `find_active_quiz_in_course()` in `authz.py`
   - ✅ Works correctly

2. **Quiz Mode Detection (exercise_detail view)**
   - Line 546: `get_quiz_context_for_course()` checks if quiz is active
   - Returns `quiz_mode=True` only when state is `display_question` or `results_for_current_question`
   - Passes `quiz_mode`, `cohort`, `quiz_module_id` to template
   - `quiz_header.html` is included when `quiz_mode=True`
   - ✅ Works correctly for active quizzes

3. **Exercise Access Permission**
   - `can_view_exercise()` checks if user is cohort member or course owner/editor/viewer
   - ✅ Basic permission works

4. **Module Flag**
   - `Module.is_quiz` field exists to mark quiz modules
   - ✅ Database structure in place

### ❌ What is NOT Working / Missing

1. **No Quiz State Enforcement for Exercise Access**
   - **Problem**: `can_view_exercise()` (line 43-52) doesn't check if exercise is in a quiz module
   - **Impact**: Student can directly visit `/exercises/<id>/` for a quiz exercise even when quiz is `not_started` or `completed`
   - **Current behavior**: They'll see the exercise WITHOUT `quiz_header.html` (because `quiz_mode=False`)
   - ❌ Students can access quiz exercises before quiz starts

2. **No Filtering in Course Details Template**
   - **Problem**: `students_course_details.html` shows ALL visible exercises (lines 53-140)
   - **No check**: Template doesn't hide exercises where `exercise.module.is_quiz == True`
   - ❌ Quiz exercises are visible in the course listing (you mentioned you hide them, but I don't see that logic in the template)

3. **No QuizLog Creation**
   - **Problem**: `QuizLog` model exists but is never created
   - `end_quiz()` in `consumers.py` (line 178-180) just sets state to `completed`
   - ❌ No persistence of completed quizzes

4. **No Way to "Clear" or "Reset" Quiz State**
   - **Problem**: Redis state persists (TTL: 2 hours)
   - Once a quiz is `completed`, restarting requires either:
     - Wait 2 hours for TTL to expire
     - Manually flush Redis
     - Or just call `start_gathering` again (which works, but state shows `completed` still in UI)
   - ❌ No clean way to reset quiz

5. **Ambiguous "Completed" State Behavior**
   - **Current**: `completed` state exists but behavior unclear
   - **Question**: Should exercises be accessible after `completed`?
   - ❌ Not specified

### 🔍 Key Questions for You

#### 1. **Quiz Exercise Visibility Rules**
Should quiz exercises be:
- **Option A**: Never shown in course details list (always hidden until quiz completes)?
- **Option B**: Shown but grayed out/disabled with a lock icon before quiz starts?
- **Option C**: Shown normally but clicking redirects to "Quiz not started" message?

#### 2. **Access Rules by Quiz State**
For a quiz exercise, what should happen when student tries to access directly via URL?

| Quiz State | Should Student See Exercise? | What Should Happen? |
|------------|------------------------------|---------------------|
| `not_started` | ❓ | Block access? Redirect? Show message? |
| `gathering` | ❓ | Redirect to waiting room? Allow access? |
| `display_question` | ✅ Yes (with quiz_header) | Current behavior OK? |
| `results_for_current_question` | ✅ Yes (with quiz_header) | Current behavior OK? |
| `completed` | ❓ | Allow normal access? Keep quiz_header? Remove restrictions? |

#### 3. **QuizLog Creation**
When should we create a `QuizLog` record?
- When teacher clicks "End Quiz"?
- What data to store? (student_count = number who submitted? number present? both?)

#### 4. **Quiz Reset/Restart**
How should teachers restart a quiz?
- **Option A**: Flush Redis state when clicking "Start Gathering" from `completed` state?
- **Option B**: Add explicit "Reset Quiz" button that clears state?
- **Option C**: Create new QuizLog and allow multiple runs (track history)?

#### 5. **Exercise Filtering Logic**
Where should we filter quiz exercises from the course details list?
- **Option A**: In the view (`course_detail`) - filter out exercises where `module.is_quiz=True` and state is not `completed`?
- **Option B**: In the template - add `{% if not exercise.module.is_quiz or quiz_completed %}`?
- **Option C**: Add a queryset method on Module to get non-quiz or completed-quiz exercises?

