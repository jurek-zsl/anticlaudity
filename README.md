# anticlaudity

[![CI](https://github.com/jurek-zsl/anticlaudity/actions/workflows/ci.yml/badge.svg)](https://github.com/jurek-zsl/anticlaudity/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Let Claude Code hand off bulk reading to Antigravity, so your Claude limits last longer.**

If you use Claude Code as your main coding agent and also have an Antigravity (Google) subscription, `anticlaudity` lets Claude delegate the cheap, token-heavy jobs (reading huge docs, scanning whole repos, digesting long logs) to the Antigravity CLI (`agy`). Claude gets back a short, structured answer instead of tens of thousands of tokens of raw source.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/jurek-zsl/anticlaudity/main/install.sh | bash
```

Then restart Claude Code so it picks up the skill. Re-run the same command to update.

**Requirements:** macOS or Linux, `python3` 3.8+, `git`, and the Antigravity CLI (`agy`) logged in. Make sure `~/.local/bin` is on your `PATH`.

<details>
<summary>Uninstall, or install by hand</summary>

```bash
# uninstall
curl -fsSL https://raw.githubusercontent.com/jurek-zsl/anticlaudity/main/uninstall.sh | bash

# manual install from a checkout
git clone https://github.com/jurek-zsl/anticlaudity && cd anticlaudity && ./install.sh
```
</details>

## How it works

```
You ──▶ Claude Code ──▶ anticlaudity ──▶ agy -p (Gemini Flash, read-only)
                ▲                              │
                └── short JSON: summary, ──────┘
                    file:line findings, confidence
```

1. The bundled **skill** (`delegate-to-antigravity`) teaches Claude when delegating is worthwhile: big inputs, short answers, mechanical work.
2. Claude runs `anticlaudity "<task>" --path <files/dirs>`.
3. The wrapper calls `agy -p` in read-only mode with a strict output schema and returns compact JSON.
4. Claude spot-checks one or two cited `file:line` references, then carries on. The raw source never enters Claude's context.

## Usage

```bash
anticlaudity "Summarize the auth flow; list file:line for each step" --path docs/spec.md --path src/auth
anticlaudity "Which tests failed and why?" --path ci.log
anticlaudity "Add a one-line docstring to every function" --path utils.py --write
anticlaudity stats --days 7
```

| Option | Meaning |
|---|---|
| `--path P` | File or directory to read (repeatable). Always pass it so scope is bounded. |
| `--model M` | Antigravity model (default `gemini-3.8-flash-medium`; list with `agy models`). |
| `--effort E` | `low`, `medium`, `high`, `xhigh`, `max`. |
| `--write` | Allow edits (`agy --mode accept-edits`). Off by default; review `git diff` afterwards. |
| `--timeout S` | Seconds before giving up (default 300). |
| `--max-findings N` | Cap on returned findings (default 15). |
| `--cwd DIR` | Working directory for `agy`. |

Output:

```json
{
  "status": "ok",
  "model": "gemini-3.8-flash-low",
  "mode": "plan",
  "duration_s": 10.3,
  "confidence": "high",
  "summary": "…",
  "findings": [{ "path": "/abs/path.py", "line": 70, "note": "…" }]
}
```

Failures return `{"status":"error","error":"…"}` with exit code 1.

Environment: `ANTICLAUDITY_MODEL`, `ANTICLAUDITY_LEDGER` (default `~/.anticlaudity/ledger.jsonl`), `ANTICLAUDITY_AGY`.

## What to delegate

| Delegate | Keep with Claude |
|---|---|
| Summarizing large docs, specs, logs | Writing or changing real code |
| Repo-wide "where is X used?" scans | Debugging non-obvious bugs |
| Extracting lists/tables/API surfaces from long files | Architecture and design decisions |
| Boilerplate, docstrings, format conversion | Security-sensitive review |
| Triaging long CI/test output | Inputs under ~5k tokens |

## Measuring the savings

Every call is logged to the ledger. `anticlaudity stats` reports:

- **Scope** handed to `agy` (estimated tokens, bytes/4).
- **Result** tokens returned to Claude.
- **Max context kept out of Claude** (scope − result). This is an **upper bound**, not a measurement: it assumes Claude would otherwise have read everything.
- Antigravity-side tokens spent, median wall time, low-confidence results, and calls that were too small to be worth delegating.

## Honest limitations

- **Fixed overhead per call:** roughly 10-20 seconds and ~18k Antigravity-side tokens, even for trivial prompts. Delegating small inputs costs more than it saves.
- **A weaker model can be wrong.** That is why results carry `confidence` and `file:line` evidence, and the skill makes Claude verify before trusting them.
- **`--write` trusts a weaker model with your files.** Use it for clearly mechanical edits and review the diff.
- The savings depend entirely on your workload. Doc-heavy and repo-exploration sessions benefit most; typical edit-and-reason sessions benefit little.

## Development

```bash
python3 -m unittest discover -s tests -v   # offline; uses a stub agy
```

CI runs the tests on Linux and macOS, ShellCheck on the scripts, and an install/uninstall round trip.

## License

[MIT](LICENSE)
