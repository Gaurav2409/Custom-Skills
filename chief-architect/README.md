# Chief Architect — Skill + Subagent

A portable "chief architect" agent: skill (knowledge + operating loop) plus
a Claude Code subagent (role + permissions). Stack-agnostic by design.

## Contents

```
chief-architect/
├── SKILL.md                          # persona, 7-phase operating loop, guardrails
├── references/
│   ├── reasoning-protocols.md        # 6 reasoning stages (step-back, Socratic
│   │                                 #   intake, analogical recall, branch/converge,
│   │                                 #   reflect-critique-refine + premortem, elenchus)
│   ├── adr-template.md               # MADR-style ADR with falsification triggers
│   ├── c4-guide.md                   # C4 levels + Mermaid recipes
│   ├── nfr-checklist.md              # quality-attribute checklist with ledger rules
│   ├── pattern-catalog.md            # patterns with when / when-NOT guidance
│   └── review-checklist.md           # tagged-verdict architecture review
└── agents/
    └── chief-architect.md            # Claude Code subagent definition
```

## Install — Claude Code

```bash
# Skill (project scope)
mkdir -p .claude/skills
cp -r chief-architect .claude/skills/chief-architect
rm -rf .claude/skills/chief-architect/agents   # subagent lives elsewhere

# Subagent
mkdir -p .claude/agents
cp chief-architect/agents/chief-architect.md .claude/agents/

# User scope instead: use ~/.claude/skills and ~/.claude/agents
```

Invoke explicitly: `Use the chief-architect subagent to design ...`
or let Claude auto-delegate on architecture tasks.

## Install — Cursor

Create `.cursor/rules/chief-architect.mdc`:

```
---
description: Chief architect mode for system design, ADRs, and architecture review
globs:
alwaysApply: false
---
When doing system design, technology selection, or architecture review,
act as chief architect: follow the operating loop in
docs/architecture/skill/SKILL.md and its references/ directory.
Plan and record decisions as ADRs before any implementation.
```

Then copy the skill folder into the repo (e.g., `docs/architecture/skill/`)
so the rule's pointer resolves. Set the rule to "Agent Requested" or attach
it manually for design sessions.

## Customizing for your stack

1. Add a `references/stack-<name>.md` with your approved services, libraries,
   and house conventions; reference it from SKILL.md Phase 3.
2. Seed `docs/adr/0001-record-architecture-decisions.md` in your repo.
3. Iterate: when the architect makes a mistake, fold the correction back
   into the relevant reference file — the skill improves with use.

## First-run smoke test

Prompt: "Design a notification service for our app. ~50k users, must feel
real-time, small team."

Expected behavior: it should refuse to design immediately — it should first
build a definitions ledger ("real-time" → ?), ask one batch of intake
questions, then produce governing principles, 2–3 candidates, an ADR with
premortem risks, a C4 context + container diagram, and handoff stories.
