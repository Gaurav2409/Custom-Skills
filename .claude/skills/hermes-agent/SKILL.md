---
name: hermes-agent
description: Launch Hermes agent with secure keychain credentials and browser-harness enabled. Use when delegating tasks or prompts to Hermes, running browser automation via Hermes, or asking "delegate to hermes", "send this to hermes", "run hermes with browser".
---

# hermes-agent delegation skill

Hermes is a local AI agent (v0.12.0) at `/Users/I321170/Documents/AI_Knowledge/hermes-agent`.

## Secure launcher

`~/.hermes/hermes-secure.sh` reads all API keys from macOS Keychain and exports them before launching hermes. It accepts all standard hermes flags via `"$@"`. This is the only way to launch hermes — never call the binary directly (keys won't be set).

Keychain entries it reads (stored under service `hermes-agent`):
- `HAI_PROXY_TOKEN` → `ANTHROPIC_API_KEY` (required — fails if missing)
- `GITHUB_TOKEN`, `EXA_API_KEY`, `FIRECRAWL_API_KEY`, `TAVILY_API_KEY`

The hermes binary resolves to `/Users/I321170/Documents/AI_Knowledge/hermes-agent/venv/bin/hermes` and connects to the Anthropic proxy at `http://localhost:6655/anthropic`.

## Enabling browser-harness

`browser-harness` is installed as a hermes skill at `~/.hermes/skills/browser-harness/`. Pass `-s browser-harness` to load it for the session.

## Delegation patterns

### One-shot task (most common for delegation)

```bash
~/.hermes/hermes-secure.sh -z "TASK_DESCRIPTION" -s browser-harness
```

- Prints only the final response to stdout. No banner, spinner, or tool previews.
- Approvals auto-bypassed.
- Use for scripted / agent-to-agent delegation.

### One-shot with specific model

```bash
~/.hermes/hermes-secure.sh -z "TASK_DESCRIPTION" -s browser-harness -m anthropic/claude-sonnet-4-6
```

Default model from config: `claude-sonnet-latest`.

### One-shot quiet (suppress session info line too)

```bash
~/.hermes/hermes-secure.sh -z "TASK_DESCRIPTION" -s browser-harness 2>/dev/null
```

### One-shot with additional toolsets

```bash
~/.hermes/hermes-secure.sh -z "TASK_DESCRIPTION" -s browser-harness -t terminal,web,file
```

### Resume last session (continue a multi-turn task)

```bash
~/.hermes/hermes-secure.sh -c -s browser-harness
```

### Resume by name

```bash
~/.hermes/hermes-secure.sh -c "session-name" -s browser-harness
```

### Isolated worktree (parallel agent on same repo)

```bash
~/.hermes/hermes-secure.sh -w -z "TASK_DESCRIPTION" -s browser-harness
```

## Browser-harness usage inside hermes

Once loaded, hermes will invoke `browser-harness -c '...'` internally when browser actions are needed. The daemon auto-starts on first use. Key helpers pre-imported in browser-harness:

```python
new_tab("https://example.com")    # first navigation (don't use goto_url first)
wait_for_load()
capture_screenshot()               # always screenshot to verify state
page_info()                        # quick liveness check
click_at_xy(x, y)                  # coordinate clicks pass through iframes/shadow DOM
js("expression")                   # DOM inspection/extraction
```

For parallel browser sessions set `BU_NAME=unique_name` before delegating.

## Delegation from Claude to Hermes (agent-to-agent)

When the user asks to delegate a task to hermes, use the Bash tool:

```bash
~/.hermes/hermes-secure.sh -z "TASK_HERE" -s browser-harness
```

Pass the full task description as the `-z` value. Hermes will use its tools (browser, terminal, web search) autonomously and return the result. Capture stdout as the result.

For long-running tasks, omit `-z` and launch interactively — but prefer `-z` for programmatic delegation since it returns a clean result.

## Common flags reference

| Flag | Purpose |
|------|---------|
| `-z "prompt"` | One-shot: single task, clean stdout output |
| `-s browser-harness` | Load browser-harness skill |
| `-m MODEL` | Override model (e.g. `anthropic/claude-sonnet-4-6`) |
| `-t TOOLSETS` | Enable toolsets: `terminal,web,file,browser` |
| `-c [name]` | Resume most recent or named session |
| `-r SESSION_ID` | Resume exact session by ID |
| `-w` | Isolated git worktree (parallel agents) |
| `--accept-hooks` | Auto-approve shell hooks (headless/CI) |
| `--yolo` | Bypass dangerous command approval prompts |
| `--checkpoints` | Filesystem checkpoints before destructive ops |
| `--max-turns N` | Max tool-calling iterations (default: 100) |

## Troubleshooting

**"HAI proxy token not found in Keychain"** — Store it:
```bash
security add-generic-password -a hermes-agent -s HAI_PROXY_TOKEN -w '<token>'
```

**Proxy not running** — hermes connects to `http://localhost:6655/anthropic`. Start the local HAI proxy before launching.

**Browser-harness daemon not connecting** — Run `browser-harness --doctor` to diagnose Chrome/CDP state.

**Session context needed** — Use `-c` or `--resume SESSION_ID` (session IDs shown on hermes exit).
