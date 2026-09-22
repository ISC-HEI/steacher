# Prompt Schema and Answer Policy

This document describes how Steacher decides what the tutor says: the prompt
template that installs the tutor's role, the layers through which a teacher can
configure it, and the schemas that constrain what the model is allowed to
return.

It covers two components named in the ELITE open-source framework deliverable (D2): the **modular prompt-schema library** and the **configurable answer-policy module**. The reflection mechanisms that promote learner self-monitoring are described under [Reflection mechanisms](#reflection-mechanisms).

Course-level tutor behavior is configurable data. The prompt lives in a
Markdown template and in database fields, so a teacher can retune the tutor for
their course without a deployment.

## Contents

- [Source files](#source-files)
- [The prompt template](#the-prompt-template)
- [Configuration layers](#configuration-layers)
- [The exercise schema](#the-exercise-schema)
- [Response schemas](#response-schemas)
- [Reflection mechanisms](#reflection-mechanisms)
- [Configuring the tutor for a course](#configuring-the-tutor-for-a-course)
- [Template rendering](#template-rendering)
- [Extending to a new subject](#extending-to-a-new-subject)

## Source files

| Concern | File |
|---|---|
| Prompt template | `steacher_app/templates/exercises/prompts/exercise_guidance.md` |
| Template rendering | `steacher_app/exercises/prompting.py` |
| Pipeline and model call | `steacher_app/exercises/logic.py` |
| Schemas | `steacher_app/exercises/schemas.py` |
| Course policy fields | `steacher_app/exercises/models.py` (`Course`) |

## The prompt template

The system prompt is a Markdown file written in Django's template language,
rendered per request against a context assembled from the exercise, its answer data, the course, and the student's language.

The template composes in a fixed order.

### 1. The role branch

The template opens by branching on one flag into two mutually exclusive roles.

**Default: the Socratic tutor.** The prompt instructs the tutor to support
independent reasoning through guiding questions. Its rules define the style
and level of assistance:

| Rule | Effect |
|---|---|
| Guide, don't give | Ask questions; never supply corrected code or formulas, even on request |
| Be concise | 2–4 short sentences, 1–2 guiding questions |
| Focus on the task | Do not close by offering further assistance |
| Respect the student's voice | Do not paraphrase the student's message back at them |
| Be precise and definitive | Never hedge with "seems correct" or "looks good"; validate the steps that are right before questioning the ones that are wrong |

The rules expand deliberately in one case: when a student says they do not
understand, the tutor may rephrase with a metaphor or example and write one or
two extra sentences.

**Alternative: the solution writer.** Reached once the student has earned the
reveal, this branch instructs the model to give the complete solution with
working code, to skip the congratulation, to ask no probing questions, and to
close by inviting follow-up.

The reveal is gated at **five recorded submissions**, and the threshold is
checked on the server. Only `run_submission` and `submit_answer` traces on the same attempt count;
hints and questions do not. A request below it returns a refusal and writes no
trace. The prompt template defines the guidance for other actions.

### 2. Conditional blocks

Three blocks then append to whichever branch was taken.

**Hint exception.** When the student presses the hint button, the template adds
a bounded exemption: the tutor may give a small snippet, a key part of a
formula, or a clearer step-by-step instruction, enough for meaningful
progress, not the whole solution, and is ordered back to Socratic style on the
next interaction. The prompt defines this behavior for each action.

**Exercise-type instructions.** Course-level instructions for this exercise
type, if the teacher set any.

**Image input.** For exercises accepting photographs, a block warns the model
that its own reading of the handwriting may be wrong. It must confirm an
uncertain line with the student, must treat a "mistake" that the student fixes
in the next step as its own misreading, and must never invent an image it did
not receive.

### 3. Course instructions

Free text the teacher attached to the course, wrapped in explicit start and end
markers that identify the course instructions in the rendered prompt.

### 4. Exercise context

The final section restates the localized question and adds the answer material
kept from the learner-facing exercise payload:

| Field | Purpose |
|---|---|
| `question_text` | The localized question selected for the student |
| `expected_result` | Marked as trustworthy; the tutor is told to trust it |
| `correct_answers` | Example solutions, with the instruction to accept **any equivalent form** |
| `hints` | Hints the tutor may use, rework, or ignore |
| `additional_context` | Anything else the teacher wants the tutor to know |

The answer fields give the tutor the reference material it needs to guide the
student. Exercises therefore separate learner-visible data from server-only
answer data.

## Configuration layers

The prompt builder selects one template and supplies course-level values in its
rendering context.

| Element | Field | Effect |
|---|---|---|
| Platform default | `exercise_guidance.md` | The Socratic tutor as shipped |
| Course replacement | `Course.override_system_prompt` | Replaces the default template when set |
| Course context | `Course.course_prompt` | Inserted by the default template for every exercise in the course |
| Type context | `Course.llm_prompts` | Inserted by the default template for one exercise type |

`course_prompt` and the selected `llm_prompts` value are plain text inserted
by the default template. They are not recursively rendered as Django templates.
When `override_system_prompt` is set, the default template is skipped. An
override must reference any context values it needs and must state the complete
tutor policy.

`llm_prompts` is a JSON dictionary keyed by exercise type:

```json
{
  "turtle": "Students have not yet seen loops. Guide with repeated commands.",
  "sql":    "Use only INNER JOIN; the course covers outer joins next week."
}
```

Both additive layers are inserted as plain text while rendering the
default template, so template syntax written inside them is not interpreted.

## The exercise schema

An exercise separates student-facing content from tutor reference material.

**`ExerciseData` — student-visible.** Includes `answer_template`, the starter
code or query the student begins from (often deliberately empty), and `db`, the
SQL database asset for SQL exercises.

**`AnswerData` — reference data.** Available to the tutor and authorized
authoring and export workflows. The learner-facing exercise payload uses
`ExerciseData`. Reference fields include:

| Field | Purpose |
|---|---|
| `hints` | One hint per line |
| `additional_context` | Prerequisites and pitfalls, shown only to the tutor |
| `expected_result` | The expected result, where applicable |
| `unit_tests` | Test cases run **before** the model is called |
| `correct_answers` | Model solutions with explanations |

### Unit tests

`UnitTests` carries `setup_code` prepended to each case, a list of `TestCase`,
and `timeout_seconds` (default 5) to stop infinite loops.

A `TestCase` holds `test_code` that exercises the student's code and prints to
stdout, and `expected_output` compared against it. The runner trims leading and
trailing whitespace from each line and from the full output. Internal blank
lines remain significant.

Tests run before the model is consulted, and their results are inserted into the
prompt. The tutor uses those results with the submitted work and the reference
answer when composing guidance. The completion marker is still generated by the
model and interpreted by the application.

## Response schemas

The model's reply is requested as JSON against a Pydantic schema. This
defines field names and value types. The prompt supplies the pedagogical
instructions, and the tutor uses the exercise context to compose its guidance.

**Text-only exchange.** One field, `guidance_text`.

**Exchange carrying images.** Four fields: `transcript` (a LaTeX transcription
of the handwriting), `error_desc` (a description of the errors found),
`text_to_highlight` (the excerpt to mark), and `guidance_text`.

**Highlight response.** `HighlightResponse` returns a `bounding_box` and a
`comment` for drawing highlight boxes over the photograph.

Each trace stores the response schema used for that reply, preserving the
structure of the original interaction.

### Response parsing

The parser processes responses in three steps: the client's parsed object, then fence-stripped
JSON, then per-field regular expressions. If all three fail, the raw body is
used as guidance when one is available.

## Reflection mechanisms

The implemented mechanisms support learner self-monitoring through guidance,
hints, and feedback within the exercise interaction.

The mechanisms are:

- **Guiding questions.** The core directive returns a question about
  the step that looks wrong, which puts the diagnostic work back on the student.
- **Validate before questioning.** The tutor names the steps that are right
  ("Your calculation of the center is correct") before questioning the ones
  that are not, so the student can localize their own error.
- **The submission threshold.** The solution unlocks after five recorded
  submissions, giving the learner time for further attempts.
- **The graduated hint.** A student who is genuinely stuck receives a direct
  next step while the complete solution remains withheld. The tutor returns to
  Socratic style immediately after.
- **Completion as an explicit judgment.** The default prompt asks the tutor to
  mark completion when all parts are correct. The server interprets the model
  marker to update the attempt. The solution-writer
  branch also requests completion and solution-revealed markers.
- **Per-reply feedback.** Students rate individual replies up or down, and
  teachers annotate whole attempts `good`, `bad`, or `unknown`.

## Configuring the tutor for a course

Course owners and editors can use the course edit form without a deployment.
The form submits `system_prompt` for `override_system_prompt` and
`llm_prompts__<type>` for each exercise-type instruction.

**Steering away from an unseen technique** — set `course_prompt`:

```
This is an introductory course. Students have covered lists and loops but not
comprehensions or generators. Do not suggest a technique the course has not
reached; guide toward a loop-based solution instead.
```

**Supplying course content.** `course_prompt` accepts a large body of text — a
summary of several thousand words is expected usage — so the tutor can refer to
the course's own material and notation in its answers.

**Per-type instructions** — set `llm_prompts` as shown above.

**Rewriting the role entirely** — set `override_system_prompt`. It is rendered
through the same strict engine against the same context, so all the variables
documented above remain available. Include the complete tutor policy and
Socratic instructions you want to apply in the replacement template.

## Template rendering

**Strict rendering.** The template engine runs with
`string_if_invalid='[[INVALID:%s]]'`, so a typo in a teacher's override renders
visibly as `[[INVALID:name]]` in the prompt.

**Plain-string output.** The rendered value is cast to `str` before it is sent
to the model. The default template explicitly disables HTML auto-escaping.

Strict missing-variable markers and the plain-string conversion apply to the
default template and course overrides. An override controls its own template
content and auto-escaping directives.

**Course policy.** Course owners and editors define the pedagogical instructions
in their templates. Review the rendered prompt and sample tutor interactions
after changing a course policy. Missing-variable markers help identify context
fields that need correction.

## Extending to a new subject

The platform is designed to extend beyond programming. Adding a subject means
deciding three things.

**1. How is the work submitted?** Existing exercise types are `python`, `sql`,
`turtle`, `scala`, and `open_question`. A subject needing no execution can use
`open_question` immediately, including photographs of handwritten work — this
is the path mathematics already takes. A subject needing a new runtime is a
larger change: prefer a WebAssembly runtime in the browser, following Pyodide
and PGlite, over a server-side service.

**2. How is correctness judged?** Existing choices include unit tests, an
expected result, and tutor judgment for an open answer. Use a deterministic
mechanism when the subject permits it.

**3. What must the tutor know or avoid?** Expressed through `course_prompt` and
`llm_prompts` without touching code.

New submission or grading mechanisms require code changes. Existing exercise
types can often be adapted through `course_prompt`, `llm_prompts`, and the
exercise answer data.
