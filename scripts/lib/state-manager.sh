#!/bin/bash
#
# Installation state management
# Tracks progress of multi-phase installation for idempotency and resumability
#

STATE_DIR="/var/lib/immich-ecosystem"
# Use persistent directory if available, fall back to /tmp for first run
if [ -d "$STATE_DIR" ] && [ -w "$STATE_DIR" ]; then
    STATE_FILE="${STATE_FILE:-$STATE_DIR/install-state.json}"
else
    STATE_FILE="${STATE_FILE:-/tmp/.immich-install-state.json}"
fi

# Initialize state file if it doesn't exist
_init_state() {
    if [ ! -f "$STATE_FILE" ]; then
        echo '{}' > "$STATE_FILE"
    fi
}

# Read a value from state JSON (requires jq or falls back to grep)
_read_state_value() {
    local key="$1"
    _init_state

    if command -v jq &>/dev/null; then
        jq -r ".[\"$key\"] // empty" "$STATE_FILE" 2>/dev/null
    else
        grep -o "\"$key\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" "$STATE_FILE" 2>/dev/null | \
            sed 's/.*: *"\([^"]*\)"/\1/'
    fi
}

# Write a value to state JSON (requires jq or falls back to simple append)
_write_state_value() {
    local key="$1"
    local value="$2"
    _init_state

    if command -v jq &>/dev/null; then
        local tmp
        tmp=$(mktemp)
        jq ".[\"$key\"] = \"$value\"" "$STATE_FILE" > "$tmp" && mv "$tmp" "$STATE_FILE"
    else
        # Fallback: simple key-value tracking via a plain text approach
        local tmp
        tmp=$(mktemp)
        grep -v "\"$key\"" "$STATE_FILE" > "$tmp" 2>/dev/null || true
        # Rebuild minimal JSON
        echo "{" > "$STATE_FILE"
        local first=true
        while IFS= read -r line; do
            line=$(echo "$line" | sed 's/[{}]//g' | xargs)
            if [ -n "$line" ]; then
                if [ "$first" = true ]; then
                    first=false
                else
                    echo "," >> "$STATE_FILE"
                fi
                echo "  $line" >> "$STATE_FILE"
            fi
        done < "$tmp"
        if [ "$first" = true ]; then
            echo "  \"$key\": \"$value\"" >> "$STATE_FILE"
        else
            echo "," >> "$STATE_FILE"
            echo "  \"$key\": \"$value\"" >> "$STATE_FILE"
        fi
        echo "}" >> "$STATE_FILE"
        rm -f "$tmp"
    fi
}

# Check if a phase has been completed
check_phase_complete() {
    local phase="$1"
    local status
    status=$(_read_state_value "${phase}_status")
    [ "$status" = "complete" ]
}

# Mark the start of a step within a phase
mark_step_start() {
    local phase="$1"
    local step="$2"
    _write_state_value "${phase}_${step}" "started"
}

# Mark a step as complete
mark_step_complete() {
    local phase="$1"
    local step="$2"
    _write_state_value "${phase}_${step}" "complete"
}

# Mark a step as failed with an error message
mark_step_failed() {
    local phase="$1"
    local step="$2"
    local error_msg="${3:-unknown error}"
    _write_state_value "${phase}_${step}" "failed"
    _write_state_value "${phase}_${step}_error" "$error_msg"
}

# Mark an entire phase as complete
mark_phase_complete() {
    local phase="$1"
    _write_state_value "${phase}_status" "complete"
    _write_state_value "${phase}_completed_at" "$(date -Iseconds)"
}
