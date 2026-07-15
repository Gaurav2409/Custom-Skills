# delegate-router — portable harness-routing skill

One `SKILL.md`, four harnesses. Installed via symlink so edits propagate everywhere.

## What it does

Picks the right harness for a task (**Claude Code**, **Cline**, **omp/oh-my-pi**, **Hermes**) and produces a clean handoff. Nothing else.

## Install

```bash
./bin/install.sh
```

Symlinks the canonical directory into:

| Harness | Path |
|---|---|
| Claude Code (personal) | `~/.claude/skills/delegate-router` |
| omp / oh-my-pi (personal) | `~/.pi/agent/skills/delegate-router` |
| Hermes (personal) | `~/.hermes/skills/multi-agent-orchestration/delegate-router` |

**Cline is project-scoped.** Install per repo:

```bash
./bin/install.sh --project /path/to/repo
```

That creates `<repo>/.cline/skills/delegate-router` **and** a `<repo>/.clinerules/00-delegate-router.md` shim (belt-and-suspenders, since Cline reliably reads `.clinerules/` even when skill auto-invocation misses).

## Verify

```bash
./bin/verify.sh
```

## Uninstall

```bash
./bin/uninstall.sh              # remove personal-scope symlinks
./bin/uninstall.sh --project /path/to/repo   # also remove per-repo files
```

## Canonical source

`~/Documents/cbc-ai/skills-repo/portable/delegate-router/`. Edit here; symlinks pick it up everywhere immediately.

## Not included

No memory / SCIF / canary / broker / cross-agent-memory logic. That's a separate skill for a system that doesn't exist yet.
