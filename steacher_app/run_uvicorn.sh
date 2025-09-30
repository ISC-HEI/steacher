#!/bin/bash

# Activate virtual environment if it exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo "✓ Virtual environment activated"
fi

# Run uvicorn with reload, watching all relevant file types
uvicorn exam_project.asgi:application \
    --host 127.0.0.1 \
    --port 8000 \
    --reload \
    --reload-dir . \
    --reload-include "*.py" \
    --reload-include "*.html" \
    --reload-include "*.css" \
    --reload-include "*.ts" \
    --reload-include "*.js" \
    --reload-exclude "node_modules/*" \
    --reload-exclude ".venv/*" \
    --reload-exclude "*.pyc" \
    --reload-exclude "__pycache__/*" \
    --reload-exclude "*.log" \
    --reload-exclude "static/js/dist/*" \
    --log-level info


