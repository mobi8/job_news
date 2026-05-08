---
name: context-manager
description: Use when the user says 이어가, 현재 상태, 컨텍스트, 정리하고 진행, context, status, continue, or when a task has accumulated many decisions/logs. Keeps work token-efficient by reading and updating docs/WORKING_CONTEXT.md before continuing.
---

# Context Manager

Purpose: keep long-running project work efficient without making the user manage context manually.

## Default behavior

When this skill is used:

1. Read `docs/WORKING_CONTEXT.md` first if it exists.
2. Run a concise status check:
   - `git status --short`
   - only inspect runtime/DB/logs if directly relevant to the user's next task.
3. Give a short state summary.
4. If context has drifted or important decisions/logs appeared, update `docs/WORKING_CONTEXT.md` before coding/running long tasks.
5. Proceed with the user's task.

## Token discipline

- Do not paste the whole context file back to the user.
- Summarize only what matters for the current task.
- Prefer updating `docs/WORKING_CONTEXT.md` over keeping long details in chat.
- Before a large run/debug/refactor/commit, checkpoint context first.

## User convenience

The user should be able to say only:

- `이어가`
- `현재 상태`
- `컨텍스트 보고 진행해`
- `정리하고 진행`

Then handle the context workflow automatically.

## Checkpoint triggers

Proactively checkpoint before continuing when:

- the conversation contains long logs or runtime errors,
- many files changed,
- a design/architecture decision changed,
- a run succeeded/failed in an important way,
- before commit/push,
- before starting a new major task.
