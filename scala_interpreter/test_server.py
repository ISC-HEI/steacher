import requests
import json
import time

BASE_URL = "http://localhost:8642"

def run_test(name, code, expected_success, expected_output_contains="", expected_error_contains="", expected_error_contains_any=None, timeout=2000):
    print(f"--- Running test: {name} ---")
    try:
        response = requests.post(f"{BASE_URL}/execute", json={"code": code, "timeoutMs": timeout})
        response.raise_for_status()
        
        data = response.json()
        print(f"Status Code: {response.status_code}")
        print(f"Response JSON: {data}")

        assert data.get("success") == expected_success, f"Expected success={expected_success}, got {data.get('success')}"
        
        if expected_output_contains:
            output = data.get("output", "")
            assert expected_output_contains in output, f"Expected output to contain '{expected_output_contains}', but got '{output}'"

        error = data.get("error", "")
        # All-of semantics
        if isinstance(expected_error_contains, list) and expected_error_contains:
            missing = [s for s in expected_error_contains if s not in error]
            assert not missing, f"Expected all of {expected_error_contains} in error, missing: {missing}. Got: '{error}'"
        elif isinstance(expected_error_contains, str) and expected_error_contains:
            assert expected_error_contains in error, f"Expected error to contain '{expected_error_contains}', but got '{error}'"

        # Any-of semantics
        if expected_error_contains_any:
            assert any(s in error for s in expected_error_contains_any), (
                f"Expected error to contain ANY of {expected_error_contains_any}, but got '{error}'"
            )

        print(f"✅ Test '{name}' PASSED")

    except requests.exceptions.RequestException as e:
        print(f"❌ Test '{name}' FAILED: Request failed: {e}")
    except Exception as e:
        print(f"❌ Test '{name}' FAILED: {e}")
    print("-" * (len(name) + 22))


if __name__ == "__main__":

    # Test 0: Success
    run_test("Hello World", "println(\"Hello, world!\")", True, expected_output_contains="Hello, world!")

    # Test 1: Successful execution with correct output
    success_code = "val x = 5 * 10; println(s\"The result is $x\")"
    run_test("Successful Execution", success_code, True, expected_output_contains="The result is 50")

    # Test 2: Execution that results in a compilation error (concise message)
    error_code = "println(someUndefinedVariable)"
    run_test(
        "Compilation Error (concise)",
        error_code,
        False,
        expected_error_contains=[
            "println(someUndefinedVariable)",
            "^",
            "not found",
        ],
    )

    # Test 3: Code that throws a runtime exception
    exception_code = """
    def divide(a: Int, b: Int): Int = a / b
    println(divide(10, 0))
    """
    run_test(
        "Runtime Exception",
        exception_code,
        False,
        expected_error_contains_any=["ArithmeticException", "/ by zero"],
    )

    # Test 4: Empty code string
    run_test("Empty Code", "", True, expected_output_contains="")

    # Test 5: Code that contains a dangerous pattern
    dangerous_code = 'val builder = new ProcessBuilder("ls")'
    run_test("Dangerous Code", dangerous_code, False)

    # Test 6: Code that takes too long to execute
    long_code = "Thread.sleep(2000)"
    run_test("Long Code", long_code, False, expected_error_contains="Timeout after 20ms", timeout=20)

    # measure time it takes over 20 requests
    start_time = time.time()
    for i in range(20):
        run_test(f"Request {i}", "println(\"Hello, world!\")", True, expected_output_contains="Hello, world!")
    took = (time.time() - start_time)/ 20 * 1000
    print(f"Time taken: {took} ms per request")
