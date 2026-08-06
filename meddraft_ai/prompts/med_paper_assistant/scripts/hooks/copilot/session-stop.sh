#!/bin/bash
# =============================================================================
# Stop Hook — Session Cleanup & Memory Sync Reminder
# =============================================================================
# Fires: when the agent session ends (user closes, timeout, or explicit stop).
# Purpose:
#   1. Remind to sync memory bank and workspace state
#   2. Finalize audit trail with session summary
#   3. Clean up transient state files (keep audit log)
# Chain: ... → PostToolUse → ... → Stop (terminal)
#
# Input: { ... }
# Output: { hookSpecificOutput: { additionalContext } }
# =============================================================================
set -e

if ! command -v jq >/dev/null 2>&1; then
    exit 0
fi

WORKSPACE_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
STATE_DIR="$WORKSPACE_ROOT/.github/hooks/_state"

# Session summary for audit
AUDIT_FILE="$STATE_DIR/session_audit.jsonl"
TOOL_COUNT=0
if [ -f "$AUDIT_FILE" ]; then
    TOOL_COUNT=$(wc -l < "$AUDIT_FILE" 2>/dev/null | tr -d ' ') || TOOL_COUNT=0
fi

# Write session end to audit
jq -n \
    --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --argjson tool_count "$TOOL_COUNT" \
    '{timestamp: $timestamp, event: "session_end", tool_count: $tool_count}' \
    >> "$AUDIT_FILE" 2>/dev/null || true

# Clean up transient state (keep audit log)
rm -f "$STATE_DIR/session_context.json" 2>/dev/null || true

# Build reminder context
CONTEXT="[SESSION ENDING] Before this session closes, ensure:"
CONTEXT="$CONTEXT\n1. sync_workspace_state(doing, next_action) — save current progress"
CONTEXT="$CONTEXT\n2. Update memory-bank/ (progress.md, activeContext.md) if significant work was done"
CONTEXT="$CONTEXT\n3. Update projects/{slug}/.memory/ (activeContext.md, progress.md) if working on a paper"
CONTEXT="$CONTEXT\n4. Total tool calls this session: $TOOL_COUNT"

jq -n \
    --arg ctx "$CONTEXT" \
    '{
        hookSpecificOutput: {
            hookEventName: "Stop",
            additionalContext: $ctx
        }
    }'
exit 0
