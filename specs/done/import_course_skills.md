# Import Tools: How This Was Built

This document describes the process and design decisions behind the exercise-generator skill and validator. Use it as a template when creating similar skills for Steacher.

## What Was Built

### 1. Exercise Generator

A Cursor Skill + standalone validator:

- **Skill** (`.cursor/skills/exercise-generator/`) — instructs an LLM to convert a teacher's Q&A pair into Steacher-importable JSON.
- **Validator** (`import_tools/validate.py`) — checks that generated JSON conforms to Steacher's Pydantic schemas, without requiring Django.

### 2. LaTeX to Course Prompt Converter

A Cursor Skill that converts a LaTeX course script (`.tex`) into a Steacher `course_prompt` markdown document:

- **Skill** (`.cursor/skills/latex-to-course-prompt/`) — strips visual-only LaTeX, preserves math and structure, wraps in the standard course prompt template.
- **No validator** — output is markdown reviewed visually.

### File Layout

```
.cursor/skills/exercise-generator/
├── SKILL.md                  # Main skill: workflow, rules, output format
├── schema-reference.md       # Field-by-field schema documentation
└── sample-exercise.json      # 2 example exercises (from a real export)

.cursor/skills/latex-to-course-prompt/
└── SKILL.md                  # Workflow, template, conversion principles

import_tools/
├── validate.py               # Standalone Pydantic validator (exercise-generator)
├── samples/                  # Reference files
│   ├── *.json                # Exported exercise JSON
│   ├── sample_script.tex     # Sample LaTeX input
│   └── sample_course_prompt.md  # Sample markdown output
└── README.md                 # This file
```

## Design Process (Q&A Rounds)

The skill was designed through structured clarification rounds before any code was written. This is the recommended approach for new skills.

### Round 1: Scope and Boundaries

Key decisions made:

| Question | Decision | Rationale |
|----------|----------|-----------|
| Exercise types in scope | `open_question` only | Math/algebra focus, no code execution needed |
| Input format | Single Q&A pair → single exercise | Keep it simple; batch generation is a future extension |
| Who consumes the prompt | An LLM (Claude, Gemini, etc.) | Teacher pastes Q&A, LLM produces JSON |
| Validator scope | Exercise schemas only (not full envelope) | Replicates `_validate_import_exercise_schemas` without Django |
| Output languages | All 3 (en, fr, de) | Required by Steacher's i18n fields |

### Round 2: Detailed Behavior

| Question | Decision | Rationale |
|----------|----------|-----------|
| Output granularity | Full import envelope (export_version, module wrapper) | Ready to upload directly into Steacher |
| Input language | French (teacher provides in French, LLM translates) | Matches the primary user base |
| Course context | Teacher provides it (course prompt or description) | LLM asks for it if not provided |
| Difficulty stars | Leave for teacher to add later | Stars are subjective; don't automate |
| `allow_image_upload` | Default `true` for open_question | Students may upload handwritten work |
| Pedagogical follow-ups | Only ask if input is ambiguous | Don't slow down clear inputs |
| `answer_template` | Usually empty for open_question | Only fill for fill-in-the-blanks |

### Round 3: Skill Format

| Question | Decision | Rationale |
|----------|----------|-----------|
| Claude.ai vs Cursor | Both — SKILL.md format works for either | Maximizes reuse |
| One skill or two | One skill with built-in validation step | Simpler for the teacher; validator still usable standalone |
| Skill storage | `.cursor/skills/` (project-level) | Shared with anyone cloning the repo |
| Two-pass workflow | Ask follow-ups only if ambiguous | Avoids unnecessary friction |
| Sample included | Yes, trimmed to 2 exercises | One straightforward, one edge case |

## How to Create a Similar Skill

### Step 1: Understand the Target Schema

- Find the Pydantic models or JSON schema that defines valid output
- Look at real examples (exported data, API responses)
- Identify which fields are required, which have defaults, and what the constraints are

### Step 2: Clarify the Workflow Through Q&A

Ask yourself (or your collaborator):

- **Input**: What does the user provide? In what language? Structured or freeform?
- **Output**: What format? Bare object or wrapped in an envelope? One item or batch?
- **Context**: What background info is needed? When should it be provided?
- **Validation**: What can go wrong? What's the minimal check to catch errors?
- **Defaults**: What should be assumed when the user doesn't specify?
- **Follow-ups**: Should the LLM always ask clarifying questions, or only when needed?

### Step 3: Write the Skill Files

Structure:

1. **SKILL.md** (~100 lines): workflow steps, generation rules, output format template. Reference other files for details.
2. **schema-reference.md**: field-by-field documentation, extracted from Pydantic models. Tables work well.
3. **sample output**: 1-2 real examples showing the target format with realistic content.
4. **Validator script** (optional): standalone script the LLM runs after generation. Copy Pydantic schemas to avoid framework dependencies.

### Step 4: Test

- Run the validator against existing real data (exported JSONs)
- Feed intentionally broken JSON to verify errors are caught
- Try the skill end-to-end: give it a Q&A pair and see if the output passes validation

## Key Patterns to Reuse

### Standalone Pydantic Validator

Copy the relevant models from the Django app into a standalone script. This avoids importing Django/DRF just for schema validation. Keep the models in sync manually — acceptable for a quick-and-dirty tool.

```python
# Copy models, replace class Config with model_config = ConfigDict(extra="ignore")
# Add custom checks (i18n keys, valid enum values) as plain functions
# Auto-detect input format (envelope vs bare object) for flexibility
# Separate errors (fatal) from warnings (non-fatal but suspicious)
```

### Progressive Disclosure in Skills

- SKILL.md has the workflow and rules (what the LLM needs to act)
- schema-reference.md has the detailed field docs (what the LLM consults when generating)
- sample JSON shows the concrete target (what "good" looks like)

### Course Context as First-Class Input

For educational content generation, the course prompt is foundational. Always ask for it upfront — it determines notation, prerequisites, concept boundaries, and tone. Without it, the LLM generates generic exercises that don't fit the course.
