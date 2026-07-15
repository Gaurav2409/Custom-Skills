---
name: delegate-router
description: Choose the right harness — Claude Code, Cline, omp/oh-my-pi, or Hermes — for a task, and produce a concise handoff. Use when deciding which agent should do coding, review, debugging, research, orchestration, or scheduled work, or when a task in progress might be better run elsewhere.
license: MIT
---

# Delegate Router

Pick the right harness for the task, then hand off cleanly. That's the whole skill.

## When to load this

- Choosing between Claude Code, Cline, omp, or Hermes for a new task.
- Mid-task: sensing the current harness is the wrong tool for what's left.
- Preparing a handoff prompt for a peer agent.

Skip if the harness is already obvious and the task is single-shot.

## Harness roles (route by task shape, not by tool name)

| Task shape | Use |
|---|---|
| Autonomous repo implementation, multi-file edits, refactors, tests | **Claude Code** |
| IDE-supervised coding, per-diff approval, Plan/Act, VS Code / JetBrains, parallel PRs via Kanban | **Cline** |
| Terminal-first coding, LSP-heavy navigation, DAP-driven debugging, harness/plugin hacking | **omp** |
| Multi-agent orchestration, deep research / MoA, KB ingestion, cron, cross-domain planning | **Hermes** |

Route by what the task needs, not by what a tool's name suggests. "omp" is not Raspberry Pi. Cline is not IDE-only. Claude Code is not Anthropic-only.

## Decision procedure

1. Is it mostly autonomous code changes across files? → **Claude Code**
2. Do you want to watch and approve every diff, or work inside the IDE? → **Cline**
3. Is a real debugger, LSP rename, or harness-internal tweak central? → **omp**
4. Does it need planning across agents, research synthesis, or recurring/scheduled work? → **Hermes**
5. Unsure? Ask one clarifying question — don't guess.

## Handoff hygiene

Before delegating between harnesses in the same repo:

- Commit or stash the working tree; don't hand over a dirty worktree.
- Name the branch; prefer a dedicated branch or `git worktree` per harness for parallel work.
- Summarize state in one paragraph: goal, what's done, what's left, known risks.
- Don't let two harnesses edit the same worktree at the same time.
- Run tests before handoff when they exist.

## Handoff prompt template

```
You are the <agent> for this task.

Goal:
Context (repo, files, prior work):
Constraints:
Do not:
Validation (how we know it's done):
Return:
```

Keep it short. If the receiving agent needs more, it will ask.

## Worked examples

- **"Refactor auth across 12 files, keep tests green"** → Claude Code. Long autonomous multi-file work with a test signal.
- **"This C binary segfaults; find the bad pointer"** → omp. DAP-attached debugging is its edge.
- **"Add a small UI tweak I want to eyeball as it happens"** → Cline. Per-diff approval in the editor.
- **"Run this analysis nightly across 40 repos and summarize"** → Hermes cron. Scheduled + cross-repo + synthesis.
- **"Research memory taxonomies for the paper"** → Hermes deep-research / MoA. Then a coding harness only if code artifacts are needed.
- **"Rename a symbol across the workspace and update imports"** → omp. LSP-driven rename lands cleanly.

## Anti-patterns

- Using Cline for long unattended work when no one will watch.
- Using Hermes as a primary code editor.
- Using Claude Code for high-volume repetitive orchestration Hermes can batch.
- Routing by tool-name vibes ("Pi in the name so it must be for Pis").
- Two harnesses editing the same worktree without a branch/worktree plan.
