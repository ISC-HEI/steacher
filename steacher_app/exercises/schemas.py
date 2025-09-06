from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class TestCase(BaseModel):
    """Pydantic model for a test case. This is used for automated unit testing. Applies to programming exercises only (e.g. Python, Scala). 
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
    test_code: str = Field(description="The test code. It should use the student's answer and `print` something to the console. For example: `print(student_function('test'))`. When you create tests, use the approach to print to console and put the expected result in the `expected_output` field**. If the user prefers to use `assert` statements, allow them to do so. The unit testing system will then run the test code and check if the output matches the expected output. If the test fails, the AI assistant will see the error message in the student's prompt and shall assess if the student code is correct.")
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
    answer_template: str = Field(default="", description="A template for the answer. It might be a starter code, a query, or a text. ATM this is not translated so choose carefully.")
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
    Hints should be in English, and the assistant will translate them into the language of the student.''')
    additional_context: str = Field(default="", description='''Additional context for the answer. This is only shown to the assistant, not to the student.
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
    For example, for a scala program to print the numbers from 1 to 10, you could include both "(1 to 10).foreach(println)" and "for (i <- 1 to 10)\\n   println(i)" as they express the same logic in different ways.''')

    class Config:
        extra = 'ignore'






def get_pydantic_schema_as_string() -> str:
    """
    Get the Pydantic schema as a string to be used in the exercise assistant prompt.
    """
    exercise_data_schema = ExerciseData.model_json_schema()
    answer_data_schema = AnswerData.model_json_schema()

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

    prompt = "The `exercise_data` field should be an object with the following properties:\n"
    prompt += format_schema(exercise_data_schema)
    prompt += "\nThe `answer_data` field should be an object with the following properties:\n"
    prompt += format_schema(answer_data_schema)

    return prompt

