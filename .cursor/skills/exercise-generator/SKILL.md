---
name: exercise-generator
description: Generate Steacher exercise JSON from question-answer pairs and course context. Handles single or multiple Q&A pairs. Use when importing exercises, creating open_question exercises, or converting Q&A into Steacher-importable JSON format. Validates output against Pydantic schemas.
---

# Steacher Exercise Generator

Convert a teacher's question-answer pair(s) into a validated Steacher import JSON file.

## Workflow

1. **Collect inputs** from the teacher:
   - **Course context** (required): the course prompt from Steacher, or a description of the course, section, and relevant concepts (notation, prerequisites, what students have/haven't learned)
   - **Question + answer pair(s)** (required): one or more exercise questions with their correct answers, typically in French. The teacher may provide a single detailed Q&A, a batch of shorter ones (e.g., a numbered list), or a LaTeX exercise file (`.tex`). When the input is a LaTeX file, parse the questions and solutions from it — they may be in bilingual format (e.g. German/French). **Always skip commented-out items** (e.g., lines starting with `%` in LaTeX) — they are intentionally excluded by the teacher.
   - **Module structure**: By default, all exercises go into one module. However, when the input contains distinct exercise groups (e.g., "derivatives", "tangent problems", "angle problems"), ask the teacher whether to split them into separate modules. Each module gets its own JSON file. When splitting, name each module as `"Serie N - Group Name"` (e.g., `"Serie 13 - Dérivées de base"`, `"Serie 14 - Optimisation"`).

2. **Ask follow-up questions** only if the input is ambiguous or missing pedagogical context. Examples of useful follow-ups:
   - Are there specific formulas or methods the student must use, or are they free to choose?
   - Should alternative solution approaches be accepted?
   - What common mistakes should the AI tutor watch for?
   - Are there concepts the student hasn't learned yet that the tutor should avoid mentioning?

3. **Generate the exercise JSON** following the schema in [schema-reference.md](schema-reference.md) and the example in [sample-exercise.json](sample-exercise.json).

4. **Validate schema** by running the validator script:
   ```bash
   python import_tools/validate.py output.json
   ```
   If validation fails, fix the errors and re-validate.

5. **Verify fidelity** against the original source material. The goal is to catch substantive changes to mathematical content or meaning — not minor grammatical adaptations (e.g., plural→singular when splitting a list into individual exercises is fine).
   - Extract all `question_i18n.fr` (or whichever language the teacher provided) and all `correct_answers[*].answer` from the JSON.
   - Compare each one against the corresponding original question/answer from the source.
   - Flag substantive differences: altered math expressions, changed notation, wrong answers, added/removed mathematical content, meaning-changing paraphrasing.
   - Present flagged differences to the teacher for review. **Do not auto-fix** — the teacher decides.
   - For large batches, use a subagent for this comparison (give it the original source and the generated JSON, ask it to list discrepancies).

6. **Return the validated JSON** to the teacher.

## Generation Rules

### Faithful Transcription (CRITICAL)

The teacher's original questions and answers are the **source of truth**. You are a transcriber, not an editor.

- **NEVER** change mathematical notation. If the teacher writes `\frac{1}{\sqrt[5]{x}}`, do not change it to `x^{-1/5}` in the question. Preserve the exact notation.
- **NEVER** modify the provided solutions. The `correct_answers[0].answer` must match the teacher's answer exactly.
- **NEVER** add mathematical content to questions that wasn't in the original (e.g., "Express your answer as..." unless the teacher wrote that).
- Minor grammatical adaptations are acceptable when restructuring (e.g., "Dériver les fonctions suivantes" → "Dériver la fonction" when splitting a list into individual exercises). But the mathematical expressions and pedagogical meaning must be preserved exactly.
- The only fields where you generate new content are: `hints`, `additional_context`, `correct_answers` beyond the first (alternative forms), and translations into languages the teacher did not provide.
- If something in the source seems wrong or ambiguous, **do not fix it** — flag it and ask the teacher.

### Languages
- Translate into all three languages: `en`, `fr`, `de`
- The teacher typically provides input in French. Translate faithfully to English and German.
- LaTeX math notation (`$...$` inline, `$$...$$` block) must be preserved identically across all three translations — do not translate math expressions.
- Markdown is supported and encouraged in `question_i18n`.

### Exercise Type
- Default to `open_question` for all exercises.
- Set `allow_image_upload: true`: Students may upload handwritten work, graphs, diagrams, etc. Students routinely photograph handwritten solutions or sketches. When an exercise asks students to draw or sketch something (e.g., graph a function), keep that instruction in the question text; students will upload an image of their drawing.

### Difficulty Stars
- Do **not** add difficulty stars (`*`, `**`, `***`) to titles. Leave that for the teacher.

### Content Guidelines
- `description_i18n`: leave as `{"en": "", "fr": "", "de": ""}` unless the teacher provides one. Don't invent descriptions.
- `exercise_data`: for open_question, typically `{"answer_template": "", "db": ""}`. Only populate `answer_template` if the question has a fill-in-the-blanks structure.
- `answer_data.hints`: progressive hints (easier to harder), in English. The AI tutor translates on-the-fly. Each hint on a new line.
- `answer_data.correct_answers`: include multiple forms of the correct answer (verbose explanation + terse/symbolic forms, alternative notations). Each with an `explanation`.
- `answer_data.additional_context`: pedagogical guidance for the AI tutor — common mistakes, edge cases, what to accept/reject, prerequisite assumptions. In English. This field is critical.
- `answer_data.unit_tests`: leave as `null` for open_question.
- `answer_data.expected_result`: leave as `null` for open_question.
- Code examples (if any) must always be in English (variable names, comments, strings).

### Output Format
The output is a **complete Steacher import envelope** containing one module with one or more exercises. Number exercises with sequential `order` values starting at 1.

```json
{
  "export_version": "1.0",
  "exported_at": "<ISO timestamp>",
  "source_course": {
    "id": 0,
    "name": "<course name>"
  },
  "module": {
    "name": "<module name>",
    "description": "",
    "order": 1,
    "visible": true,
    "is_quiz": false,
    "exercises": [
      {
        "title_i18n": {"en": "...", "fr": "...", "de": "..."},
        "description_i18n": {"en": "", "fr": "", "de": ""},
        "question_i18n": {"en": "...", "fr": "...", "de": "..."},
        "exercise_type": "open_question",
        "order": 1,
        "exercise_data": {"answer_template": "", "db": ""},
        "answer_data": { ... },
        "visible": true,
        "allow_image_upload": true
      }
    ]
  },
  "asset_references": []
}
```

Set `source_course.id` to `0` and `source_course.name` to whatever the teacher says the course is.

When producing multiple modules, generate one JSON file per module (each with its own envelope). Use distinct `module.order` values (1, 2, 3, ...).

### Large Batches

For exercise sheets with many sub-problems (10+), use a systematic approach:
- Create a todo list with one item per module
- For computation-style exercises (derivatives, integrals, etc.), the structure is repetitive: use subagents per module to parallelize
- Always validate every generated file

When delegating to subagents, include in the prompt:
- The full JSON envelope skeleton (don't ask the subagent to read schema files)
- All exercises for that module inlined as a compact list: `[letter] function → answer | technique`
- The generation rules from this skill (faithful transcription, escaping, languages)
- Remind about JSON escaping: LaTeX `\frac` must be `\\frac` in JSON strings
- The output file path

### Computation-Style Exercises

For exercises that ask "find the derivative/integral/limit of..." with many sub-items:
- **Titles**: use the series numbering (e.g., "1a", "1b", ...) — same across all 3 languages
- **Question pattern**: "Dériver la fonction $x \mapsto ...$." / "Find the derivative of..." / "Bestimmen Sie die Ableitung..."
- **Hints pattern**: (1) identify the technique, (2) state the relevant rule, (3) apply it step by step
- **additional_context pattern**: name the technique(s), warn about common mistakes (forgotten chain rule, sign errors, missing absolute values), list equivalent forms to accept
- **Simplification exercises**: when the function simplifies before differentiating (e.g., `sin(arcsin(x)) = x`), make the simplification insight the main pedagogical point

### Output Directory

Write generated JSON files to `import_tools/imported_exercises/`. Create the directory if it doesn't exist.

## Additional Resources

- Full JSON schema with field descriptions: [schema-reference.md](schema-reference.md)
- Example of well-formed exercises: [sample-exercise.json](sample-exercise.json)
- Standalone validator: `import_tools/validate.py`
