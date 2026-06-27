---
name: kanban-worker
description: Pattern library for kanban worker agents — summary/metadata shapes, retry diagnostics, block-reason examples, and workspace conventions. Auto-loaded by the dispatcher for every task.
user-invocable: false
---

# Kanban Worker — Pattern Library

This skill is the deeper reference for kanban worker agents. The mandatory lifecycle
is injected via KANBAN_GUIDANCE in the system prompt; this document provides the
patterns, examples, and conventions that make handoffs reliable.

## Summary Shapes

When calling `kanban_complete(summary=..., metadata=...)`, follow these patterns:

### Good summary examples

- "Added retry-with-backoff to the PDF upload endpoint. Changed files: `src/upload.py`, `tests/test_upload.py`. All 14 tests pass."
- "Feasibility assessment complete: FaceFusion requires CUDA 11.8+ and 8GB+ VRAM for face_swapper model. Kaggle T4 (16GB VRAM, CUDA 12.1) is compatible. Draft notebook saved to workspace."
- "Blocked: API rate limit hit after 200 requests. Need premium key or cooldown period (24h). Partial results saved."

### Bad summary examples (do NOT do this)

- "Done." (no artifacts, no evidence)
- "I think it works now" (no test results, no changed files)
- "See the code" (no specifics)

## Metadata Shapes

`metadata` is a JSON dict for machine-readable facts. Common keys:

```json
{
  "changed_files": ["src/foo.py", "tests/test_foo.py"],
  "tests_run": 14,
  "tests_passed": 14,
  "tests_failed": 0,
  "decisions": ["Used retry pattern instead of queue"],
  "artifacts": ["notebook_facefusion_kaggle.ipynb"],
  "compatibility": {"cuda": "12.1", "vram_gb": 16, "python": "3.11"},
  "dependencies_installed": ["onnxruntime-gpu", "insightface"]
}
```

Only include keys that are relevant. Do not fabricate metrics.

## Block Reasons

Use `kanban_block(reason=...)` only for genuine ambiguity requiring human decision.

### Valid block reasons

- "review-required: Refactored auth module, needs security review before merge"
- "missing-credentials: Need HuggingFace API token to download gated model"
- "ambiguous-spec: Task says 'optimize' but doesn't specify latency vs throughput"
- "dependency-blocked: Waiting on task t_abc123 to provide training data"
- "resource-limit: Need GPU with 24GB VRAM; current environment only has 16GB"

### Invalid block reasons (do NOT block for these)

- "I'm not sure how to proceed" (try something, document what you tried)
- "This might be wrong" (run tests, verify, then report findings)
- "Takes too long" (heartbeat and keep working, or complete with partial results)

## Retry Diagnostics

If you are a retry worker (your task has prior crashed/blocked runs):

1. Call `kanban_show()` to read prior run errors and comments
2. Check `last_failure_error` in the task data
3. Address the root cause — do not repeat the same approach that crashed
4. If the failure is environmental (missing deps, wrong Python version), fix it in the workspace before proceeding
5. If the failure is a bug in your approach, switch strategies
6. Comment your diagnosis with `kanban_comment` before proceeding

## Workspace Conventions

- `cd $HERMES_KANBAN_WORKSPACE` before any file operations
- Keep all work within the workspace directory
- If you need a git worktree: `git worktree add $HERMES_KANBAN_WORKSPACE <branch>`
- Clean up temporary files before completing
- Leave a README or notes file if the workspace has non-obvious structure

## Heartbeat Pattern

For long operations (training, encoding, crawling, large installs):

```
kanban_heartbeat(note="Installing dependencies... (step 3/7)")
kanban_heartbeat(note="Training epoch 5/20, loss=0.342")
kanban_heartbeat(note="Crawling page 150/500")
```

Heartbeat every few minutes. Skip for short tasks (< 5 minutes).

## Common Pitfalls

1. Do NOT shell out to `hermes kanban <verb>` — use the `kanban_*` tools
2. Do NOT complete a task you did not actually finish — block it instead
3. Do NOT put secrets/tokens/PII in summary or metadata — these are stored forever
4. Do NOT assign follow-up work to yourself — use `kanban_create` with the right assignee
5. Do NOT call `delegate_task` as a board substitute — delegate_task is for in-run subtasks