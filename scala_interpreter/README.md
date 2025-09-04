# Scala Interpreter REST Server

This project provides a simple REST server that can execute arbitrary Scala code using the Ammonite interpreter. The goal is to have a sub 100ms latency for the execution of the code, in a failsafe way (kinda detect fraudulent code, and restart the service on failure.



## How to use with Docker

Needed to code locally.

    docker rm -f scala-interpreter-container || true
    docker build --no-cache --build-arg BUILD_PLATFORM=linux/amd64 -t scala-interpreter-container .
    docker run -d -p 8642:8642 --name scala-interpreter-container scala-interpreter-container
    docker logs --tail 50 scala-interpreter-container | cat
    python test_server.py

