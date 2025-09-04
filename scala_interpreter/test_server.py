import requests
import json
import time

BASE_URL = "http://localhost:8642"

def run_test(name, code, expected_success, expected_output_contains="", expected_error_contains=""):
    print(f"--- Running test: {name} ---")
    try:
        response = requests.post(f"{BASE_URL}/execute", json={"code": code})
        response.raise_for_status()
        
        data = response.json()
        print(f"Status Code: {response.status_code}")
        print(f"Response JSON: {data}")

        assert data.get("success") == expected_success, f"Expected success={expected_success}, got {data.get('success')}"
        
        if expected_output_contains:
            output = data.get("output", "")
            assert expected_output_contains in output, f"Expected output to contain '{expected_output_contains}', but got '{output}'"

        if expected_error_contains:
            error = data.get("error", "")
            assert expected_error_contains in error, f"Expected error to contain '{expected_error_contains}', but got '{error}'"

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

    # Test 2: Execution that results in a compilation error
    error_code = "println(someUndefinedVariable)"
    run_test("Compilation Error", error_code, False)

    # Test 3: Code that throws a runtime exception
    exception_code = """
    def divide(a: Int, b: Int): Int = a / b
    println(divide(10, 0))
    """
    run_test("Runtime Exception", exception_code, False)

    # Test 4: Empty code string
    run_test("Empty Code", "", True, expected_output_contains="")

    # Test 5: Code that contains a dangerous pattern
    dangerous_code = 'val builder = new ProcessBuilder("ls")'
    run_test("Dangerous Code", dangerous_code, False)

    # Test 6: Code that takes too long to execute
    long_code = "for (i <- 1 to 10000000) { println(i) }"
    run_test("Long Code", long_code, False, expected_error_contains="Timeout after 2000ms")

    # measure time it takes over 20 requests
    start_time = time.time()
    for i in range(20):
        run_test(f"Request {i}", "println(\"Hello, world!\")", True, expected_output_contains="Hello, world!")
    took = (time.time() - start_time)/ 20 * 1000
    print(f"Time taken: {took} ms per request")
