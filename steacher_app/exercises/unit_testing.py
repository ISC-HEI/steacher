'''
Runs unit tests on student code in a safe and isolated manner.
For now, this module provides functions to execute Python code in a separate process.
TODO: Replace with a proper sandbox environment for security.
'''

import io
import traceback
from contextlib import redirect_stdout, redirect_stderr
import requests
from django.conf import settings
import logging
import multiprocessing

logger = logging.getLogger(__name__)

def normalize_output(output: str) -> str:
    """Normalizes output for comparison by trimming whitespace from each line and the overall string."""
    if not isinstance(output, str):
        return ""
    return "\n".join(line.strip() for line in output.strip().split('\n'))

def _execute_code_in_process(code: str, q: multiprocessing.Queue):
    """Target function for the multiprocessing process to execute code safely."""
    try:
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        # Redirect stdout and stderr to capture output
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            # Use a restricted global scope
            restricted_globals = {
                "__builtins__": __builtins__
            }
            exec(code, restricted_globals)

        stdout = stdout_capture.getvalue()
        stderr = stderr_capture.getvalue()
        q.put({"stdout": stdout, "stderr": stderr, "exception": None})

    except Exception as e:
        # Capture any exception that occurs during execution
        exc_info = traceback.format_exc()
        q.put({"stdout": "", "stderr": str(e), "exception": exc_info})

def execute_code_isolated(code: str, timeout: int = 5) -> tuple[str, str, str | None]:
    """
    ISOLATED EXECUTION FUNCTION - FIXME Replace this when moving to a sandbox.
    Executes code in a separate process to isolate it and enforce a timeout.

    Returns: (stdout, stderr, exception_traceback)
    """
    q = multiprocessing.Queue()
    process = multiprocessing.Process(target=_execute_code_in_process, args=(code, q))

    process.start()
    process.join(timeout=timeout)

    if process.is_alive():
        process.terminate() # Terminate the process if it runs for too long
        process.join()
        return "", "TimeoutError: Code execution exceeded the time limit.", "TimeoutError"

    try:
        result = q.get_nowait()
        return result["stdout"], result["stderr"], result["exception"]
    except Exception:
        return "", "An unknown error occurred during code execution.", "UnknownError"

def run_single_test(setup_code: str, student_code: str, test_case: dict, timeout: int) -> dict:
    """Runs a single test case and returns its result."""
    test_code = test_case.get("test_code", "")
    full_code = f"{setup_code}\n\n{student_code}\n\n{test_code}"

    stdout, stderr, exception = execute_code_isolated(full_code, timeout)

    normalized_stdout = normalize_output(stdout)
    expected_output = normalize_output(test_case.get("expected_output", ""))

    passed = not exception and not stderr and (normalized_stdout == expected_output)

    error_message = None
    if exception:
        error_message = f"An exception occurred: {stderr}\nTraceback:\n{exception}"
    elif stderr:
        error_message = f"An error was reported: {stderr}"

    return {
        "description": test_case.get("description", "Unnamed test"),
        "test_code": test_code,
        "passed": passed,
        "actual_output": stdout,
        "expected_output": test_case.get("expected_output", ""),
        "error": error_message
    }

def run_unit_tests(student_code: str, unit_tests_data: dict) -> dict:
    """
    Main entry point for running unit tests.
    """
    setup_code = unit_tests_data.get("setup_code", "")
    test_cases = unit_tests_data.get("test_cases", [])
    timeout = unit_tests_data.get("timeout_seconds", 5)

    if not test_cases:
        return {"all_passed": True, "passed_count": 0, "failed_count": 0, "total_count": 0, "execution_error": None, "test_results": []}

    results = []
    passed_count = 0

    # First, check if the student's code can compile on its own
    try:
        compile(student_code, "<string>", "exec")
    except SyntaxError as e:
        return {
            "all_passed": False, "passed_count": 0, "failed_count": len(test_cases), "total_count": len(test_cases),
            "execution_error": f"Syntax Error in your code: {e}",
            "test_results": []
        }

    for test_case in test_cases:
        result = run_single_test(setup_code, student_code, test_case, timeout)
        if result["passed"]:
            passed_count += 1
        results.append(result)

    return {
        "all_passed": passed_count == len(test_cases),
        "passed_count": passed_count,
        "failed_count": len(test_cases) - passed_count,
        "total_count": len(test_cases),
        "execution_error": None,
        "test_results": results
    }

"""Language-agnostic formatters live below; prefer format_test_results_for_ai_with_lang."""


def run_unit_tests_scala(student_code: str, unit_tests_data: dict) -> dict:
    """Run Scala unit tests by calling the scala_interpreter service per test."""
    setup_code = unit_tests_data.get("setup_code", "")
    test_cases = unit_tests_data.get("test_cases", [])
    if not test_cases:
        return {"all_passed": True, "passed_count": 0, "failed_count": 0, "total_count": 0, "execution_error": None, "test_results": []}

    results = []
    passed_count = 0
    base_url = f"{getattr(settings, 'SCALA_INTERPRETER_URL', 'http://scala_interpreter:8642')}/execute"

    for test_case in test_cases:
        test_code = test_case.get("test_code", "")
        full_code = f"{setup_code}\n\n{student_code}\n\n{test_code}"
        try:
            r = requests.post(base_url, json={"code": full_code}, timeout=20)
            r.raise_for_status()
            data = r.json() or {}
            actual_out = normalize_output(str(data.get("output") or ""))
            expected = normalize_output(test_case.get("expected_output", ""))
            passed = bool(data.get("success")) and (actual_out == expected)
            if passed:
                passed_count += 1
            results.append({
                "description": test_case.get("description", "Unnamed test"),
                "test_code": test_code,
                "passed": passed,
                "actual_output": str(data.get("output") or ""),
                "expected_output": test_case.get("expected_output", ""),
                "error": str(data.get("error") or "") or None,
            })
        except Exception as e:
            results.append({
                "description": test_case.get("description", "Unnamed test"),
                "test_code": test_code,
                "passed": False,
                "actual_output": "",
                "expected_output": test_case.get("expected_output", ""),
                "error": str(e),
            })

    return {
        "all_passed": passed_count == len(test_cases),
        "passed_count": passed_count,
        "failed_count": len(test_cases) - passed_count,
        "total_count": len(test_cases),
        "execution_error": None,
        "test_results": results,
    }


def format_test_results_for_ai_with_lang(results: dict, language: str) -> str:
    """Same as format_test_results_for_ai but with language tag in code fences."""
    if not results or not results.get("test_results"):
        if results.get("execution_error"):
            return f"The student's code could not be tested due to an error:\n{results['execution_error']}"
        return "No test results available."

    output = f"Passed: {results['passed_count']}/{results['total_count']} tests\n\n"
    if results.get('execution_error'):
        output += f"**Execution Error:** {results['execution_error']}\n\n"

    for test in results['test_results']:
        status = "✓ PASSED test" if test['passed'] else "✗ FAILED test"
        output += f"### {status}: {test['description']}\n"
        output += f"**Test code:**\n```{language}\n{test['test_code']}\n```\n"
        if not test['passed']:
            if test.get('error'):
                output += f"**Error:**\n```\n{test['error']}\n```\n"
            else:
                output += f"**Expected output:**\n```\n{test['expected_output']}\n```\n"
                output += f"**Actual output from student's code:**\n```\n{test['actual_output']}\n```\n"
            output += "=> The student's code did not produce the expected result for this test case.\n"
        output += "\n---\n"
    return output
