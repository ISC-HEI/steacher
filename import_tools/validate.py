#!/usr/bin/env python3
"""Standalone validator for Steacher exercise import JSON files.
Validates exercise_data and answer_data against Pydantic schemas without Django dependencies."""

import json
import sys
from pathlib import Path
from typing import Optional, List, Any

try:
    from pydantic import BaseModel, ConfigDict, Field, ValidationError
except ImportError:
    print("ERROR: pydantic is required. Install with: pip install pydantic", file=sys.stderr)
    sys.exit(1)


# --- Pydantic schemas (copied from steacher_app/exercises/schemas.py) ---

REQUIRED_LANGUAGES = {"en", "fr", "de"}
VALID_EXERCISE_TYPES = {"python", "sql", "scala", "turtle", "open_question"}


class TestCase(BaseModel):
    description: str = Field(default="")
    test_code: str = Field(default="")
    expected_output: str = Field(default="")


class UnitTests(BaseModel):
    setup_code: str = Field(default="")
    test_cases: List[TestCase] = Field(default_factory=list)
    timeout_seconds: int = Field(default=5)


class CorrectAnswer(BaseModel):
    answer: str = Field(default="")
    explanation: str = Field(default="")


class ExerciseData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    answer_template: str = Field(default="")
    db: str = Field(default="")


class AnswerData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    hints: str = Field(default="")
    additional_context: str = Field(default="")
    expected_result: Optional[Any] = Field(default=None)
    unit_tests: Optional[UnitTests] = Field(default=None)
    correct_answers: List[CorrectAnswer] = Field(default_factory=list)


# --- Validation logic ---

def validate_i18n(field_name: str, value: Any) -> list[str]:
    """Check that an i18n field is a dict with en/fr/de keys."""
    errors = []
    if not isinstance(value, dict):
        errors.append(f"{field_name}: expected dict, got {type(value).__name__}")
        return errors
    missing = REQUIRED_LANGUAGES - set(value.keys())
    if missing:
        errors.append(f"{field_name}: missing language keys: {', '.join(sorted(missing))}")
    return errors


def validate_exercise(ex: dict, index: int) -> list[str]:
    """Validate a single exercise dict. Returns list of error strings."""
    errors = []
    prefix = f"exercise[{index}]"

    # i18n fields
    for field in ("title_i18n", "description_i18n", "question_i18n"):
        if field not in ex:
            errors.append(f"{prefix}: missing required field '{field}'")
        else:
            errors.extend(f"{prefix}.{e}" for e in validate_i18n(field, ex[field]))

    # exercise_type
    ex_type = ex.get("exercise_type")
    if not ex_type:
        errors.append(f"{prefix}: missing required field 'exercise_type'")
    elif ex_type not in VALID_EXERCISE_TYPES:
        errors.append(f"{prefix}: invalid exercise_type '{ex_type}' (valid: {', '.join(sorted(VALID_EXERCISE_TYPES))})")

    # order
    if "order" not in ex:
        errors.append(f"{prefix}: missing required field 'order'")

    # exercise_data
    try:
        ExerciseData.model_validate(ex.get("exercise_data", {}))
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(l) for l in err["loc"])
            errors.append(f"{prefix}.exercise_data.{loc}: {err['msg']}")

    # answer_data
    try:
        AnswerData.model_validate(ex.get("answer_data", {}))
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(l) for l in err["loc"])
            errors.append(f"{prefix}.answer_data.{loc}: {err['msg']}")

    # Warnings (non-fatal)
    ad = ex.get("answer_data", {})
    if not ad.get("correct_answers"):
        errors.append(f"{prefix} [WARNING]: answer_data.correct_answers is empty")
    if not ad.get("hints"):
        errors.append(f"{prefix} [WARNING]: answer_data.hints is empty")
    if not ad.get("additional_context"):
        errors.append(f"{prefix} [WARNING]: answer_data.additional_context is empty")

    return errors


def validate_json(data: dict) -> list[str]:
    """Validate a Steacher import JSON. Accepts full envelope or bare exercise."""
    errors = []

    # Detect format: full envelope vs bare exercise
    if "module" in data and "exercises" in data.get("module", {}):
        exercises = data["module"]["exercises"]
        if not isinstance(exercises, list):
            return ["module.exercises: expected a list"]
    elif "exercise_type" in data:
        exercises = [data]
    else:
        return ["Unrecognized format: expected either a full import envelope (with 'module.exercises') or a bare exercise (with 'exercise_type')"]

    if not exercises:
        return ["No exercises found"]

    for i, ex in enumerate(exercises):
        errors.extend(validate_exercise(ex, i))

    return errors


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <json_file> [<json_file> ...]", file=sys.stderr)
        sys.exit(1)

    exit_code = 0
    for filepath in sys.argv[1:]:
        path = Path(filepath)
        if not path.exists():
            print(f"ERROR: file not found: {filepath}", file=sys.stderr)
            exit_code = 1
            continue

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"ERROR: invalid JSON in {filepath}: {e}", file=sys.stderr)
            exit_code = 1
            continue

        errors = validate_json(data)
        warnings = [e for e in errors if "[WARNING]" in e]
        real_errors = [e for e in errors if "[WARNING]" not in e]

        print(f"\n{'=' * 60}")
        print(f"  {filepath}")
        print(f"{'=' * 60}")

        if real_errors:
            print(f"\n  ERRORS ({len(real_errors)}):")
            for e in real_errors:
                print(f"    - {e}")
            exit_code = 1
        if warnings:
            print(f"\n  WARNINGS ({len(warnings)}):")
            for w in warnings:
                print(f"    - {w}")
        if not real_errors and not warnings:
            print("\n  OK - all exercises valid")
        elif not real_errors:
            print(f"\n  VALID (with {len(warnings)} warnings)")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
