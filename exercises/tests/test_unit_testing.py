import unittest
from exercises.unit_testing import normalize_output, run_unit_tests, format_test_results_for_ai

class TestUnitTesting(unittest.TestCase):

    def test_normalize_output(self):
        """Tests that normalize_output correctly trims whitespace."""
        self.assertEqual(normalize_output("  hello  \n  world  "), "hello\nworld")
        self.assertEqual(normalize_output("\n\n a \n b \n\n"), "a\nb")
        self.assertEqual(normalize_output("singleline"), "singleline")
        self.assertEqual(normalize_output(""), "")

    def test_run_unit_tests_all_passing(self):
        """Tests a scenario where the student's code is correct and all tests pass."""
        student_code = "def add(a, b):\n    return a + b"
        unit_tests_data = {
            "test_cases": [
                {
                    "description": "Test with positive numbers",
                    "test_code": "print(add(2, 3))",
                    "expected_output": "5"
                },
                {
                    "description": "Test with negative numbers",
                    "test_code": "print(add(-1, -1))",
                    "expected_output": "-2"
                }
            ]
        }
        results = run_unit_tests(student_code, unit_tests_data)
        self.assertTrue(results["all_passed"])
        self.assertEqual(results["passed_count"], 2)
        self.assertEqual(results["failed_count"], 0)
        self.assertEqual(len(results["test_results"]), 2)
        self.assertTrue(results["test_results"][0]["passed"])
        self.assertTrue(results["test_results"][1]["passed"])

    def test_run_unit_tests_one_failing(self):
        """Tests a scenario where the student's code has a logic error."""
        student_code = "def add(a, b):\n    return a - b  # Incorrect logic"
        unit_tests_data = {
            "test_cases": [
                {
                    "description": "Test with positive numbers",
                    "test_code": "print(add(5, 2))",
                    "expected_output": "7"
                }
            ]
        }
        results = run_unit_tests(student_code, unit_tests_data)
        self.assertFalse(results["all_passed"])
        self.assertEqual(results["passed_count"], 0)
        self.assertEqual(results["failed_count"], 1)
        self.assertFalse(results["test_results"][0]["passed"])
        self.assertEqual(normalize_output(results["test_results"][0]["actual_output"]), "3")

    def test_run_unit_tests_with_exception(self):
        """Tests a scenario where the student's code raises an exception."""
        student_code = "def divide(a, b):\n    return a / b"
        unit_tests_data = {
            "test_cases": [
                {
                    "description": "Test division by zero",
                    "test_code": "print(divide(10, 0))",
                    "expected_output": ""
                }
            ]
        }
        results = run_unit_tests(student_code, unit_tests_data)
        self.assertFalse(results["all_passed"])
        self.assertEqual(results["failed_count"], 1)
        self.assertIsNotNone(results["test_results"][0]["error"])
        self.assertIn("ZeroDivisionError", results["test_results"][0]["error"])

    def test_run_unit_tests_with_syntax_error(self):
        """Tests a scenario where the student's code has a syntax error."""
        student_code = "def add(a, b)\n    return a + b"  # Missing colon
        unit_tests_data = {"test_cases": [{"test_code": "print(add(1, 1))"}]}
        results = run_unit_tests(student_code, unit_tests_data)
        self.assertFalse(results["all_passed"])
        self.assertEqual(results["failed_count"], 1)
        self.assertIsNotNone(results["execution_error"])
        self.assertIn("Syntax Error", results["execution_error"])

    def test_run_unit_tests_timeout(self):
        """Tests a scenario where the code execution times out."""
        student_code = "import time\nwhile True:\n    time.sleep(0.1)"
        unit_tests_data = {
            "timeout_seconds": 1,
            "test_cases": [
                {
                    "description": "Infinite loop test",
                    "test_code": "print('This will not be reached')",
                    "expected_output": ""
                }
            ]
        }
        results = run_unit_tests(student_code, unit_tests_data)
        self.assertFalse(results["all_passed"])
        self.assertEqual(results["failed_count"], 1)
        self.assertIsNotNone(results["test_results"][0]["error"])
        self.assertIn("TimeoutError", results["test_results"][0]["error"])

    def test_format_test_results_for_ai(self):
        """Tests that the AI formatting function produces the expected output."""
        results = {
            "all_passed": False,
            "passed_count": 1,
            "failed_count": 1,
            "total_count": 2,
            "execution_error": None,
            "test_results": [
                {
                    "description": "Correct addition", "passed": True, "test_code": "print(add(2, 2))",
                    "actual_output": "4\n", "expected_output": "4", "error": None
                },
                {
                    "description": "Incorrect subtraction", "passed": False, "test_code": "print(add(5, 2))",
                    "actual_output": "3\n", "expected_output": "7", "error": None
                }
            ]
        }
        formatted_string = format_test_results_for_ai(results)
        self.assertIn("✓ PASSED test: Correct addition", formatted_string)
        self.assertIn("✗ FAILED test: Incorrect subtraction", formatted_string)
        self.assertIn("Expected output", formatted_string)
        self.assertIn("Actual output", formatted_string)
        self.assertIn("Passed: 1/2 tests", formatted_string)

    def test_format_test_results_with_syntax_error(self):
        """Tests AI formatting for a syntax error."""
        results = {
            "all_passed": False, "passed_count": 0, "failed_count": 1, "total_count": 1,
            "execution_error": "Syntax Error in your code: invalid syntax",
            "test_results": []
        }
        formatted_string = format_test_results_for_ai(results)
        self.assertIn("could not be tested", formatted_string)
        self.assertIn("Syntax Error", formatted_string)

if __name__ == '__main__':
    unittest.main()
