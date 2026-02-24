# Steacher Exercise JSON Schema Reference

## Exercise Fields (top level per exercise)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title_i18n` | `{"en": str, "fr": str, "de": str}` | Yes | Localized titles. Stars (`*`, `**`) at the start indicate difficulty — don't add them unless asked. Must not hint at the solution. |
| `description_i18n` | `{"en": str, "fr": str, "de": str}` | Yes | Short localized descriptions. Often empty — that's fine. Must not hint at the solution. |
| `question_i18n` | `{"en": str, "fr": str, "de": str}` | Yes | Full question text. Markdown supported. Use LaTeX for math (`$...$`). |
| `exercise_type` | `str` | Yes | One of: `python`, `sql`, `scala`, `turtle`, `open_question`. |
| `order` | `int` | Yes | Position within the module (1-based). |
| `exercise_data` | `ExerciseData` | Yes | See below. |
| `answer_data` | `AnswerData` | Yes | See below. |
| `visible` | `bool` | Yes | Whether the exercise is visible to students. Default `true`. |
| `allow_image_upload` | `bool` | Yes | Whether students can upload images. Default `true` for open_question. |

## ExerciseData

For `open_question`, this is typically empty.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `answer_template` | `str` | `""` | Starter text or template. Usually empty. Use for fill-in-the-blanks (e.g., `"a = \nb ="`). |
| `db` | `str` | `""` | SQL exercises only — name of the database asset file. |

## AnswerData

Backend-only data (not shown to students). Write all fields in **English** — the AI tutor translates on-the-fly.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `hints` | `str` | `""` | Progressive hints (easier → harder), each on a new line. Guide without revealing the solution. |
| `additional_context` | `str` | `""` | Pedagogical guidance for the AI tutor: common mistakes, edge cases, what to accept/reject, prerequisite assumptions, concepts to avoid. **Critical field.** |
| `expected_result` | `any` | `null` | Simple expected output (for SQL, simple Python). Leave `null` for open_question. |
| `unit_tests` | `UnitTests\|null` | `null` | Automated tests (programming exercises only). Leave `null` for open_question. |
| `correct_answers` | `list[CorrectAnswer]` | `[]` | Multiple correct answer forms. See below. |

## CorrectAnswer

| Field | Type | Description |
|-------|------|-------------|
| `answer` | `str` | The correct answer text. Include multiple entries for different valid forms (symbolic, verbose, alternative notations). |
| `explanation` | `str` | Why this is correct. Can include the solution steps. |

## Import Envelope

The full JSON file wraps exercises in a module:

```
{
  "export_version": "1.0",
  "exported_at": "<ISO timestamp>",
  "source_course": {"id": int, "name": str},
  "module": {
    "name": str,
    "description": str,
    "order": int,
    "visible": bool,
    "is_quiz": bool,
    "exercises": [ ...exercise objects... ]
  },
  "asset_references": []
}
```
