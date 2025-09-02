# Scala Interpreter REST Server

This project provides a simple REST server that can execute arbitrary Scala code using the Ammonite interpreter.

## Prerequisites

-   [sbt](https://www.scala-sbt.org/download.html) (Scala Build Tool)
-   [Python 3](https://www.python.org/downloads/)
-   The `requests` library for Python. You can install it using pip:
    ```bash
    pip install requests
    ```

## How to Run the Server

1.  Open a terminal in the root directory of the project.
2.  Start the server using the `sbt run` command:
    ```bash
    sbt run
    ```
3.  The server will start and listen on `http://localhost:8080`.

## How to Run the Tests

The tests are written in Python and use the `requests` library to send requests to the running server.

1.  Make sure the server is running in a separate terminal.
2.  Open another terminal in the root directory of the project.
3.  Run the tests using the following command:
    ```bash
    python test_server.py
    ```
4.  You will see the output of the tests in the console, indicating whether they passed or failed.

## How to Use Docker

    docker rm -f scala-interpreter-test || true
    docker build --no-cache --build-arg BUILD_PLATFORM=linux/amd64 -t scala-interpreter-server .
    docker run -d -p 8080:8080 --name scala-interpreter-test scala-interpreter-server
    docker logs --tail 50 scala-interpreter-test | cat
    python test_server.py