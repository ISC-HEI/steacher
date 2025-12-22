#!/bin/bash

# redeploy on prod

LOGFILE="redeploy.log"

# Function to run a command and only show output if it fails
run_cmd() {
    local description="$1"
    shift
    echo "Running: $description" | tee -a "$LOGFILE"
    
    # Capture both stdout and stderr to a temp file
    local temp_output=$(mktemp)
    
    # Run the command, capturing output
    if "$@" >> "$temp_output" 2>&1; then
        # Success - append to log only
        cat "$temp_output" >> "$LOGFILE"
        echo "✓ Success" | tee -a "$LOGFILE"
        rm "$temp_output"
        return 0
    else
        # Failure - show output to console and log
        echo "✗ FAILED" | tee -a "$LOGFILE"
        cat "$temp_output" | tee -a "$LOGFILE"
        rm "$temp_output"
        return 1
    fi
}

echo "=== Redeploy started at $(date) ===" | tee "$LOGFILE"

# 1) Get latest code
run_cmd "git pull" git pull || exit 1

# 3) Build the web image (so collectstatic runs against the new code)
run_cmd "docker compose build web" docker compose build web || exit 1

# 4) Collect static into STATIC_ROOT and write manifest
run_cmd "collectstatic" docker compose run --rm --no-deps --entrypoint "" web python manage.py collectstatic --noinput || exit 1

# 5) Recreate/start the app with the new image
run_cmd "docker compose up web" docker compose up -d --no-deps web || exit 1

# 6) Apply DB migrations if models changed
run_cmd "migrate" docker compose exec web python manage.py migrate || exit 1

# 7) somehow needed
run_cmd "restart web proxy" docker compose restart web proxy || exit 1

echo "=== Redeploy completed successfully at $(date) ===" | tee -a "$LOGFILE"

