from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class UnitTests(BaseModel):
    """Pydantic model for unit tests structure."""
    setup_code: str = ""
    test_cases: List[Dict[str, str]] = Field(default_factory=list)
    timeout_seconds: int = 5


class Choice(BaseModel):
    """Pydantic model for a multiple-choice option."""
    id: str
    text: str


class CorrectAnswer(BaseModel):
    """Pydantic model for a correct answer in multiple choice."""
    answer: str
    explanation: str = ""


class ExerciseData(BaseModel):
    """
    Unified Pydantic model for the `exercise_data` JSON field.
    Contains all possible fields across different exercise types.
    """
    additional_context: str = ""
    answer_template: str = ""
    db: str = ""  # SQL only
    choices: List[Choice] = Field(default_factory=list)  # Multiple Choice only

    class Config:
        # Prevents errors if extra fields are present in the JSON
        # but not defined in the model.
        extra = 'ignore'


class AnswerData(BaseModel):
    """
    Unified Pydantic model for the `answer_data` JSON field.
    Contains all possible fields for backend-only answer data.
    """
    hints: List[str] = Field(default_factory=list)
    additional_context: str = ""
    expected_result: Optional[Any] = None
    unit_tests: UnitTests = Field(default_factory=UnitTests)  # Python/Scala
    correct_answers: List[CorrectAnswer] = Field(default_factory=list)  # Multiple Choice

    class Config:
        extra = 'ignore'
