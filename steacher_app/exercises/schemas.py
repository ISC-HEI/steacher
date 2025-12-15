import json
import logging
import re

from typing import Optional, List, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def strip_markdown_fences(content: str) -> str:
    """Removes Markdown code fences (e.g., ```json) from a string."""
    content = content.strip()
    if content.startswith("```"):
        # Find the first newline
        first_newline = content.find('\n')
        if first_newline != -1:
            content = content[first_newline + 1:]
        else:  # Should not happen with valid markdown but handle it
            content = content.lstrip('`')

    if content.endswith("```"):
        content = content[:-3].strip()
    return content


class TutorResponse(BaseModel):  # used for structured output validation with Gemini API.
    """
    Response from AI tutor (exercise guidance or study chat). For example, 
```json
{
  "transcript" : "$y = x - 8$\\n$y = 3x + 1$\\n$x - 8 = 3x + 1$\\n$-2x = 9$\\n$x = 4.5$\\n$y = x - 8 = 4.5 - 8 = 3.5$",
  "error_desc" : "The exercise description asks to solve for y = x + 8",
  "text_to_highlight" : "$y = x - 8$",
  "guidance_text" : "You should check again your signs in the first equation."
}
```
    """
    transcript: Optional[str] = Field(
        default="",
        description="A complete LaTeX retranscription of the student worksheet picture, if provided. In case you didn't receive an image, simply leave this field empty. Must be written in valid LaTeX format. Include the student's paging, line breaks, etc. Illustrations and graphs should be replaced by a short description of their content. The content of this field is not shown to the student. Ensure all LaTeX backslashes are double-escaped (e.g., \\frac instead of \frac) so the output remains valid JSON. For teacher debugging only."
    )
    error_desc: Optional[str] = Field(
        default="",
        description="A concise description of the mistakes made by the student that you spotted. For teacher debugging only."
    )
    text_to_highlight: Optional[str] = Field(
        default="",
        description="An extract of the transcript with the exact text containing the student mistake."
    )
    guidance_text: str = Field(
        description="The Socratic guidance text for the student. This is the only field shown to the student."
    )    

    def to_dict(self) -> dict:
        """Convert to dictionary format matching existing assistant_content structure in Trace model."""
        return {
            "guidance_text": self.guidance_text,
            "error_desc": self.error_desc or "",
            "transcript": self.transcript or "",
            "text_to_highlight": self.text_to_highlight or "",
        }

    @classmethod
    def from_gemini_response(cls, response: Any) -> 'TutorResponse':
        """
        Factory method to create a TutorResponse from a Google GenAI response object.
        Prioritizes strict JSON parsing (response.parsed) but falls back to text parsing.
        """
        # 1. Try the SDK's automatic parsing (if available and successful)
        if hasattr(response, 'parsed') and response.parsed:
            try:
                if isinstance(response.parsed, cls):
                    return response.parsed
                if isinstance(response.parsed, dict):
                    return cls(**response.parsed)
            except Exception as e:
                logger.warning(f"response.parsed present but validation failed: {e}")

        # 2. Fallback: Parse the raw text manually
        # Handle cases where response.text might be None
        raw_text = getattr(response, 'text', '') or ''
        return cls.parse_text(raw_text)

    @staticmethod
    def parse_text(text_out: str) -> 'TutorResponse':
        """Parses a raw string (with potential Markdown fences) into TutorResponse."""
        if not text_out:
            return TutorResponse(guidance_text="")

        try:    
            # Remove markdown code fences
            text_out = strip_markdown_fences(text_out)

            # Attempt clean JSON parse
            try:
                loaded_response = json.loads(text_out)
                return TutorResponse(**loaded_response)
            except Exception as e:
                logger.warning(f"Failed to load response as JSON: {e}. Falling back to Regex.")
                
            # Regex Fallbacks (try to extract a key field from the text and match until the next key or the end of the text is reached)
            guidance_match = re.search(r'guidance[_ ]text:\s*(.*?)(?:transcript[_ ]:|error[_ ]description:|highlighted[_ ]text[_ ]:|$)', text_out, re.DOTALL | re.IGNORECASE)
            transcript_match = re.search(r'transcript[_ ]:\s*(.*?)(?:guidance[_ ]text:|error[_ ]description:|highlighted[_ ]text[_ ]:|$)', text_out, re.DOTALL | re.IGNORECASE)
            error_desc_match = re.search(r'error[_ ]description:\s*(.*?)(?:guidance[_ ]text:|transcript[_ ]:|highlighted[_ ]text[_ ]:|$)', text_out, re.DOTALL | re.IGNORECASE)
            highlighted_text_match = re.search(r'highlighted[_ ]text[_ ]:\s*(.*?)(?:guidance[_ ]text:|transcript[_ ]:|error[_ ]description:|$)', text_out, re.DOTALL | re.IGNORECASE)
            
            if guidance_match:
                loaded_response = {
                    "guidance_text": guidance_match.group(1).strip(),
                    "transcript": transcript_match.group(1).strip() if transcript_match else "",
                    "error_desc": error_desc_match.group(1).strip() if error_desc_match else "",
                    "highlighted_text" : highlighted_text_match.group(1).strip() if highlighted_text_match else ""
                }
            else:
                # Last resort: treat whole text as guidance
                loaded_response = {"guidance_text": text_out}

            return TutorResponse(**loaded_response)

        except Exception as e:
            logger.exception(f"Error parsing TutorResponse from text: {e}")
            return TutorResponse(guidance_text=text_out)


class HighlightResponse(BaseModel):
    """
    Response from AI text finder (find_text_in_image). For example: 
```json
{
  "bounding_box" : "[10, 100, 70, 140]",
  "comment" : ""
}
```
    """
    bounding_box: List[int] = Field(
        default_factory=list,
        description="2D bounding box [y0, x0, y1, x1] or empty if not found"
    )
    comment: str = Field(
        default="",
        description="Error message or empty if successful"
    )
    elapsed_time: float = Field(
        default=0.0,
        description="Time taken for API call in seconds"
    )
    
    @classmethod
    def from_gemini_response(cls, response: Any, elapsed_time: float) -> 'HighlightResponse':
        """
        Factory method to create a HighlightResponse from a Google GenAI response object.
        Prioritizes strict JSON parsing (response.parsed) but falls back to text parsing.
        
        Args:
            response: The Gemini API response object
            elapsed_time: Time taken for the API call in seconds
        """
        # 1. Try the SDK's automatic parsing (if available and successful)
        if hasattr(response, 'parsed') and response.parsed:
            try:
                if isinstance(response.parsed, dict):
                    parsed_dict = response.parsed.copy()
                    parsed_dict['elapsed_time'] = elapsed_time
                    return cls(**parsed_dict)
            except Exception as e:
                logger.warning(f"response.parsed present but validation failed: {e}")

        # 2. Fallback: Parse the raw text manually
        raw_text = getattr(response, 'text', '') or ''
        return cls.parse_text(raw_text, elapsed_time)
    
    @staticmethod
    def parse_text(text_out: str, elapsed_time: float = 0.0) -> 'HighlightResponse':
        """Parses a raw string (with potential Markdown fences) into HighlightResponse."""
        if not text_out:
            return HighlightResponse(
                bounding_box=[],
                comment="ERROR: Empty response",
                elapsed_time=elapsed_time
            )

        try:
            # Remove markdown code fences
            text_out = strip_markdown_fences(text_out)

            # Attempt clean JSON parse
            try:
                loaded_response = json.loads(text_out)
                loaded_response['elapsed_time'] = elapsed_time
                return HighlightResponse(**loaded_response)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to load response as JSON: {e}. Falling back to regex.")
            
            # Regex fallback to extract bounding_box and comment
            bbox_match = re.search(r'bounding[_ ]box["\s:]*\[([\d,\s]+)\]', text_out, re.IGNORECASE)
            comment_match = re.search(r'comment["\s:]*"([^"]*)"', text_out, re.IGNORECASE)
            
            bounding_box = []
            if bbox_match:
                try:
                    bounding_box = [int(x.strip()) for x in bbox_match.group(1).split(',')]
                except ValueError:
                    logger.warning(f"Failed to parse bounding box coordinates: {bbox_match.group(1)}")
            
            comment = comment_match.group(1) if comment_match else "ERROR: Failed to parse response"
            
            return HighlightResponse(
                bounding_box=bounding_box,
                comment=comment,
                elapsed_time=elapsed_time
            )

        except Exception as e:
            logger.exception(f"Error parsing HighlightResponse from text: {e}")
            return HighlightResponse(
                bounding_box=[],
                comment=f"ERROR: {str(e)}",
                elapsed_time=elapsed_time
            )


class TestCase(BaseModel):
    """Pydantic model for a test case. This is used for automated unit testing. Applies to programming exercises only (e.g. Python, Scala).
    Never just write a `description` without a `test_code`. You may omit the `expected_output` if your `test_code` uses assertions, but if it prints something to the console, you must have an `expected_output`.
    The AI assistant will not have to run the unit tests itself, as it will be run by the system. The AI assistant will see the test results in the student's prompt and shall assess if the student code is correct.
    Exceptions in the code cause the test to fail, so make sure to handle them. You don't need to use a try/except block, just let the exception bubble up.
    Avoid non-deterministic tests, like tests that depend on the order of elements in a list. If necessary (e.g. working with random numbers), make sure to set the seed to a fixed value.
    Extra output beyond `expected_output` will cause the test to fail.
    State does not persist between test cases.
    Here is a simple example, with an exercise that is a function taking a list of numbers and returns the sum of the numbers
    - `test_code`: `print(sum([1, 2, 3]))`
    - `expected_output`: `6`
    """
    description: str = Field(default="", description="The description of the test case, in English. Not strictly mandatory, but make sure you create one to give context to the test case. The description is not shared with the student, but is used by the AI assistant to understand the test case.")
    test_code: str = Field(description="The test code. It should use the student's code (e.g. a function that the student has written) and `print` something to the console. For example: `print(student_function('test'))`. When you create tests, use the approach to print to console and put the expected result in the `expected_output` field**. If the user prefers to use `assert` statements, allow them to do so. The unit testing system will then run the test code and check if the output matches the expected output. If the test fails, the AI assistant will see the error message in the student's prompt and shall assess if the student code is correct.")
    expected_output: str = Field(default="", description="The expected output of the test code in the console (stdout only). This should be a case-sensitive exact match of type string, including newlines. Both the output of running the `test_code` and the value of the `expected_output` field will be trimmed of leading and trailing whitespace prior to comparison. For a test that prints the number 15, this should just be '15'. For a test that prints the numbers 1 to 4 on separate lines, this should be '1\\n2\\n3\\n4'. Blank lines are significant. The unit testing system will then run the test code and check if the output matches the expected output. If you don't have an expected output, leave this field empty.")


class UnitTests(BaseModel):
    """Pydantic model for unit tests structure."""
    setup_code: str = Field(default="", description="Setup code that will be prepended to each test case. Optional. Typically used to set up the environment for the tests, like importing modules or defining helper functions.")
    test_cases: List[TestCase] = Field(default_factory=list, description="List of test cases.")
    timeout_seconds: int = Field(default=5, description="Timeout in seconds per test case. To prevent infinite loops.")


class CorrectAnswer(BaseModel):
    """Pydantic model for a correct answer."""
    answer: str = Field(description="The correct answer. For example, for an open question it would be the chosen answer text (with justifications if applicable). For a programming exercise, this should be the complete, runnable code for a correct solution.")
    explanation: str = Field(default="", description="An explanation of why this is the correct answer. It can include some context on why the answer is correct, or what approach has been used to find the answer.")


class ExerciseData(BaseModel):
    """
    Unified Pydantic model for **exercise data** in the `exercise_data` JSON field.
    Not all question types require all these fields, so leave them empty if not applicable.
    For backend and frontend, so this data is shown to the student.
    """
    answer_template: str = Field(default="", description="A template for the answer. It might be a starter code, a query, or a text. ATM this is not translated so write it in English.")
    db: str = Field(default="", description="For SQL exercises only. The name of the database asset file to use.")

    class Config:
        # Prevents errors if extra fields are present in the JSON
        # but not defined in the model.
        extra = 'ignore'


class AnswerData(BaseModel):
    """
    Unified Pydantic model for **answer data** in the `answer_data` JSON field.
    Not all question types require all these fields, so leave them empty if not applicable.
    Backend only, so the student does not see these fields (because it includes answers, hints, etc. which should not be shown to the student).
    """
    hints: str = Field(default="", description='''A string containing hints, with each hint on a new line. 
    It is not mandatory for the assistant to use the hints, but it should help it understand the exercise context and generate better hints.
    Hints should be in English, and the assistant will translate them into the language of the student. Ideally, hints should be progressive (easier → harder).''')
    additional_context: str = Field(default="", description='''Additional context for the answer. This is only shown to the assistant, not to the student. It may include prerequisite assumptions.
    It could include additional information about the exercise, the context in which it is to be solved, etc. For example, if the students have not yet learned about a specific technique, 
    you could instruct the assistant not to talk about it.
    Else you could also instruct the assistant to be quite permissive into the correct answers, because the question is exploratory and the correct answer is not always obvious.''')
    expected_result: Optional[Any] = Field(default=None, description='''The expected result of the exercise, if applicable.
    Use `unit_tests` for comprehensive testing of programming exercises. If `unit_tests` are provided, they take precedence over this field.
    This field should be used for simpler cases where there's only a single, simple output to check (e.g., the result of a single SQL query). If you don't have an expected result, leave this field empty.
    For example, for a SQL exercise, it would be the result of a query. For a simple python exercise that prints to the console, it would be the content of the console output. For an open question, it would be the expected answer.''')
    unit_tests: UnitTests = Field(default_factory=UnitTests, description="The unit tests to run (if applicable). These tests will be run by the system and the results will be added to the student's prompt for the assistant.")
    correct_answers: List[CorrectAnswer] = Field(default_factory=list, description='''A list of correct answers to this question. 
    It's recommended to include multiple correct answers that reflect the expected diversity of student responses. It's the job of the assistant to propose an exhaustive list of correct answers.
    For example, for a scala program to print the numbers from 1 to 10, you could include both "(1 to 10).foreach(println)" and "for (i <- 1 to 10)\\n   println(i)" as they express the same logic in different ways.
    For turtle exercises, the answer is Python code that will be executed via Pyodide to draw the correct pattern on canvas (rendered as reference in gray).''')

    class Config:
        extra = 'ignore'






def get_pydantic_schema_as_string() -> str:
    """
    Get the Pydantic schema as a string to be used in the exercise assistant prompt.
    """

    def format_schema(schema, indent=0):
        output = ""
        for key, value in schema.get('properties', {}).items():
            output += ' ' * indent + f"- `{key}`"
            if 'type' in value:
                output += f" ({value['type']})"
            if 'description' in value:
                output += f": {value['description']}"
            if 'items' in value:
                if 'properties' in value['items']:
                    output += "\n" + format_schema(value['items'], indent + 2)
                elif '$ref' in value['items']:
                     # Find the referenced schema in the definitions
                    ref_name = value['items']['$ref'].split('/')[-1]
                    ref_schema = schema.get('$defs', {}).get(ref_name)
                    if ref_schema:
                        output += f", where each item is an object with the following properties:\n" + format_schema(ref_schema, indent + 2)
            output += "\n"
        return output

    exercise_data_schema_str = format_schema(ExerciseData.model_json_schema())
    answer_data_schema_str = format_schema(AnswerData.model_json_schema())

    prompt = f"""
    
### Top-level Exercise fields
- `pk` (integer, read-only): The primary key of the exercise. Do not modify.
- `title_i18n` (object): The title of the exercise in English, German, and French. Make sure that the title does not give away any hints about the exercise's solution.
  - `en` (string): English title.
  - `de` (string): German title.
  - `fr` (string): French title.
- `order` (integer, read-only): The display order of the exercise within its module.
- `description_i18n` (object, optional): A short description of the exercise in English, German, and French. Leave it empty if it doesn't add value. Description should be concise and to the point. E.g. "Conditional statements and the modulo operator." instead of "An exercise to practice conditional statements and the modulo operator.". Description must not give away any hints about the exercise's solution (a bad example would be "Using the `LIKE` operator to filter by a pattern and `ORDER BY` to sort the results." because this would indicate that the student should use the `LIKE` and `ORDER BY` operators). 
  - `en` (string): English description.
  - `de` (string): German description.
  - `fr` (string): French description.
- `question_i18n` (object): The full question or prompt for the exercise in English, German, and French. Markdown is supported and encouraged.
  - `en` (string): English question.
  - `de` (string): German question.
  - `fr` (string): French question.
- `exercise_type` (string): The type of the exercise (one of `python`, `sql`, `open_question`, `scala`, `turtle`). Determines the structure of `exercise_data`. Modify only if it makes sense.
- `allow_image_upload` (boolean): Whether students can upload images as part of their answer (e.g., photos of handwritten work, diagrams, or screenshots). Useful for exercises where visual content is part of the solution.
- `available_sql_assets` (array of strings, read-only): For SQL exercises, a list of available database assets. Can be used to set up the db field in `exercise_data` below.
- `course_pk` (integer, read-only): The primary key of the course this exercise belongs to. Do not modify.
- `course_name` (string, read-only): The name of the course this exercise belongs to. Do not modify.
- `course_description` (string, read-only): The description of the course this exercise belongs to. Use this to get some context about the course. Do not modify.

### Exercise Data Schema (`exercise_data`)
{exercise_data_schema_str}

### Answer Data Schema (`answer_data`)
{answer_data_schema_str}

"""

    return prompt

