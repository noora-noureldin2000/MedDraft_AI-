#!/bin/bash
# =============================================================================
# PreCompact Hook — Memory Checkpoint Before Context Compaction
# =============================================================================
# Fires: before VS Code Copilot compacts (summarizes) conversation context.
# Purpose:
#   1. Inject reminder to save critical state before context is truncated
#   2. Summarize current session state for the compacted context
#   3. List active files and unsaved changes
# Chain: ... → PostToolUse → ... → PreCompact → [compaction] → Agent continues
#
# Input: { sessionId?, ... }
# Output: { hookSpecificOutput: { additionalContext } }
# =============================================================================
set -e

if ! command -v jq >/dev/null 2>&1; then
    exit 0
fi

WORKSPACE_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
STATE_DIR="$WORKSPACE_ROOT/.github/hooks/_state"
mkdir -p "$STATE_DIR"

# Gather current state
MODE="normal"
DOING=""
NEXT_ACTION=""
ACTIVE_PROJECT=""
WRITING_SECTION=""

# Read mode
MODE_FILE="$WORKSPACE_ROOT/.copilot-mode.json"
if [ -f "$MODE_FILE" ]; then
    MODE=$(jq -r '.mode // "normal"' "$MODE_FILE" 2>/dev/null) || MODE="normal"
fi

# Read workspace state
STATE_FILE="$WORKSPACE_ROOT/.mdpaper-state.json"
if [ -f "$STATE_FILE" ]; then
    DOING=$(jq -r '.doing // empty' "$STATE_FILE" 2>/dev/null) || true
    NEXT_ACTION=$(jq -r '.next_action // empty' "$STATE_FILE" 2>/dev/null) || true
    ACTIVE_PROJECT=$(jq -r '.active_project // empty' "$STATE_FILE" 2>/dev/null) || true
    WRITING_SECTION=$(jq -r '.writing_session.section // empty' "$STATE_FILE" 2>/dev/null) || true
fi

# Count tool invocations in this session
AUDIT_FILE="$STATE_DIR/session_audit.jsonl"
TOOL_COUNT=0
if [ -f "$AUDIT_FILE" ]; then
    TOOL_COUNT=$(wc -l < "$AUDIT_FILE" 2>/dev/null | tr -d ' ') || TOOL_COUNT=0
fi

# Build context for post-compaction
CONTEXT="[PRE-COMPACT CHECKPOINT] Context is being compacted. Critical state to preserve:"
CONTEXT="$CONTEXT\n- Mode: $MODE"
if [ -n "$DOING" ]; then CONTEXT="$CONTEXT\n- Doing: $DOING"; fi
if [ -n "$NEXT_ACTION" ]; then CONTEXT="$CONTEXT\n- Next: $NEXT_ACTION"; fi
if [ -n "$ACTIVE_PROJECT" ]; then CONTEXT="$CONTEXT\n- Project: $ACTIVE_PROJECT"; fi
if [ -n "$WRITING_SECTION" ]; then CONTEXT="$CONTEXT\n- Writing: $WRITING_SECTION"; fi
CONTEXT="$CONTEXT\n- Tool calls this session: $TOOL_COUNT"
CONTEXT="$CONTEXT\n\nACTION REQUIRED: Before proceeding, call sync_workspace_state() and checkpoint_writing_context() if actively writing. Also call get_workspace_state() after compaction to recover full context."

jq -n \
    --arg ctx "$CONTEXT" \
    '{
        hookSpecificOutput: {
            hookEventName: "PreCompact",
            additionalContext: $ctx
        }
    }'
exit 0
