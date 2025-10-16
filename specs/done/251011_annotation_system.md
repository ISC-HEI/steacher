# Manual Attempt Annotation System

## Background

Steacher is an AI-powered educational platform where students work through programming exercises with the help of an LLM tutor that uses the Socratic method. A critical challenge in this system is ensuring that exercises are well-designed: the exercise instructions must be clear enough, and provide sufficient context for the AI tutor to effectively guide students through various failure modes.

The initial goal was to build an **a priori validation system** that would test exercises before students encountered them. Inspired by the evaluation framework from "Evaluating LLMs" by Shreya Shankar and Hamel Husain (2025), the proposed system would:

1. **Generate failure modes**: Use an LLM to imagine all possible student errors (syntax errors, misconceptions, logic errors, edge cases)
2. **Plan simulations**: Organize these into discrete test scenarios
3. **Simulate students**: Run multiple simulated "students" in parallel, each embodying a specific failure mode, creating real Attempts and Traces
4. **Judge performance**: Have an LLM judge evaluate whether the AI tutor successfully handled each failure mode

This would have allowed teachers to validate exercises by simulating dozens of student interactions before deployment, catching issues where the exercise lacks sufficient scaffolding for the tutor to succeed.

## Why We Chose Manual Annotation Instead

After reading the evals course material, particularly the emphasis on the **Analyze-Measure-Improve lifecycle**, it became clear that the proposed automated system had a fundamental flaw: **we cannot validate an automated evaluation system without ground truth from real data**.

The course emphasizes:
- "There is no substitute for examining real outputs on real data" (Section 1.3)
- The **Gulf of Comprehension** must be bridged through manual analysis first (Section 3)
- "If you are not willing to look at some data manually on a regular cadence you are wasting your time" (Hamel's note, Section 1.4)
- Open coding on real examples is essential before building automated evals

The proposed system would have been **LLMs evaluating LLMs all the way down**:
- LLM generates failure modes
- LLM simulates students  
- LLM acts as tutor
- LLM judges the interaction

Without real student data to validate against, we'd just be testing "can one LLM convince another LLM that tutoring happened?" rather than whether real students would be well-served.

**The right approach:** Start with the **Analyze phase** - systematically review real student attempts to build a taxonomy of actual failure modes. Only then can we:
1. Validate whether LLM-generated failure modes match reality
2. Build reliable automated evaluators
3. Know what "good tutoring" actually looks like

## Implementation

We built a streamlined manual annotation tool following evaluation best practices from the course material.

### Data Model

**AttemptEval** model tracks teacher annotations:
- `attempt`: Link to student's Attempt
- `is_ok`: Boolean (True=good, False=bad, None=unknown)  
- `feedback`: Free-form text comments
- `annotator`: Teacher who created the evaluation
- Unique constraint: one evaluation per annotator per attempt

### Backend (`views_annotations.py`)

Two views handle the workflow:

**Entry point** (`annotate_exercise_entry`):
- Finds first unannotated attempt for an exercise
- Redirects to annotation view

**Main view** (`annotate_attempt`):
- Displays exercise question, conversation traces, and final code
- Shows progress (X of Y annotated)
- Handles form submission with three navigation options:
  - Previous
  - Next  
  - **Next Unannotated** (primary action)

Helper functions efficiently query for unannotated attempts using Django ORM with proper indexing.

### UI Design

**Two-column layout:**

**Left (70%)** - Attempt review:
- Collapsible exercise question with hints, context, correct answers, and external link
- Chronological conversation display with color-coded interaction types:
  - 🔴 Red: Solution revealed (`reveal_solution`)
  - 🟡 Yellow: Hint requested (`ask_hint`)  
  - 🔵 Blue: Question asked (`ask_question`)
  - ⚪ Light blue: Regular submission
- Student code shown per trace (collapsible)
- Execution results (collapsible)

**Right (30%, sticky)** - Annotation form:
- Progress bar
- Radio buttons: Good (1) / Bad (2) / Unknown (3)
- Comments textarea (4)
- Navigation buttons (Z for save & next)
- "All done" notification when complete

### Keyboard Shortcuts

Optimized for rapid annotation:
- `1` / `2` / `3`: Select evaluation
- `4`: Focus on comments  
- `Z`: Save and go to next unannotated

Shortcuts are disabled while typing and show as small numbered tags with hover tooltips. This allows experienced annotators to move through attempts quickly without touching the mouse.

### Integration

Added "Annotate" button (clipboard-check icon) to each exercise in the teacher course details page, positioned next to Analytics and before Delete.

## Current State

This is a **basic annotator** implementing the Analyze phase of the evaluation lifecycle. It provides:

✅ Systematic review of real student attempts  
✅ Binary failure classification (good/bad/unknown)  
✅ Free-form notes for capturing observed patterns  
✅ Progress tracking  
✅ Fast keyboard-driven workflow  
✅ Visual highlighting of key interactions (hints, questions, solution reveals)  

This establishes the foundation for "open coding" as described in Section 3 of the evaluation framework.

## Next Steps

Following the Analyze-Measure-Improve lifecycle, the natural progression is:

### Phase 1: Axial Coding (Structure Failure Modes)
- **Add failure mode categorization UI**: After annotating ~20-50 attempts, allow teachers to:
  - Review all "bad" attempts
  - Group similar failures into categories
  - Define structured failure mode taxonomy
  - LLM-assisted clustering of open-coded annotations
- **Export annotations**: Generate CSV/JSON of annotations for external analysis

### Phase 2: Quantification
- **Dashboard**: Show failure mode distribution per exercise
- **Cohort comparison**: Track which exercises cause the most difficulty
- **Temporal analysis**: Monitor if changes to exercises reduce failure rates

### Phase 3: Validation of Automated System
Now that we have real data, revisit the original automated validation idea:
- Run failure mode generator on annotated exercises
- **Compare**: Do LLM-generated failure modes match real student failures?
- **Measure precision/recall**: Did it predict the right problems?
- Only if validation shows >70% overlap, proceed with automated simulation

### Phase 4: Measure (Automated Evaluators)
- Build LLM-as-Judge evaluators for specific failure modes
- Validate judges against human annotations (calculate TPR, TNR)
- Use corrected failure rate estimates (Rogan-Gladen formula)

### Phase 5: Improve (Close the Loop)
- Suggest exercise improvements based on failure patterns
- A/B test changes and measure impact
- Guide teachers on which exercises need better scaffolding

## Key Lessons from the Evals Course Applied

1. **Start with qualitative analysis**: Manual review reveals nuances that automated systems miss
2. **Binary labels over Likert scales**: Forces clear thinking about what constitutes failure
3. **Representative data is essential**: Test on real student diversity, not generic benchmarks
4. **Iteration is normal**: Expect 2-3 rounds of annotation to reach theoretical saturation
5. **Validate before automating**: Ground truth from humans is the foundation for LLM judges

The current implementation respects these principles by focusing on building a solid foundation of human-labeled data before attempting automation. This "slower" approach will ultimately lead to a more reliable and trustworthy evaluation system.



