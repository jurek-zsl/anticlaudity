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
3. The wrapper splits big scopes into chunks (default ~40k tokens each), runs them through `agy -p` in parallel and read-only with a strict output schema, and merges them into one compact JSON.
4. Claude spot-checks one or two cited `file:line` references, then carries on. The raw source never enters Claude's context.

## Usage

```bash
anticlaudity "Summarize the auth flow; list file:line for each step" --path docs/spec.md --path src/auth
anticlaudity "Which tests failed and why?" --path ci.log
anticlaudity "Add a one-line docstring to every function" --path utils.py --write
anticlaudity "Map the architecture" --path src --dry-run   # show the chunk plan, send nothing
anticlaudity stats --days 7
```

### Big projects

Scopes are expanded to a file list (skipping `node_modules`, `.git`, lockfiles and binaries) and cut into chunks, so no single `agy` call has to swallow the whole project. If a chunk times out or comes back empty, it is retried and then split in half; whatever was covered is still returned, and anything that wasn't is listed in `uncovered_files` with `status: "partial"`. Scopes needing more than `--max-chunks` chunks are refused up front, with a hint to narrow `--path`.

For large scopes (more than ~100k tokens), run it in the background, since Claude Code's shell tool gives up on a command after 10 minutes. Use `--dry-run` first to see the plan.

| Option | Meaning |
|---|---|
| `--path P` | File or directory to read (repeatable). Always pass it so scope is bounded. |
| `--model M` | Antigravity model (default `gemini-3.8-flash-medium`; list with `agy models`). |
| `--effort E` | `low`, `medium`, `high`, `xhigh`, `max`. On `gemini-…-low/medium/high` models this swaps the model's suffix (agy rejects the two together); `xhigh`/`max` are ignored there. |
| `--write` | Allow edits (`agy --mode accept-edits`). Off by default; review `git diff` afterwards. |
| `--timeout S` | Seconds per `agy` call before it is killed (default 420). |
| `--max-findings N` | Approximate total findings, shared across chunks (default 15). |
| `--chunk-tokens N` | Target source size per `agy` call (default 40000). |
| `--jobs N` | Parallel `agy` calls (default 3; always 1 with `--write`). |
| `--max-chunks N` | Refuse scopes needing more chunks than this (default 20). |
| `--dry-run` | Print the chunk plan and exit without calling `agy`. |
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
  "findings": [{ "path": "/abs/path.py", "line": 70, "note": "…" }],
  "est_claude_tokens_saved": 41200
}
```

`status` is `ok`, `partial` (some files not covered; see `uncovered_files`) or `error` (exit code 1, `{"status":"error","error":"…"}`).

Environment: `ANTICLAUDITY_MODEL`, `ANTICLAUDITY_LEDGER` (default `~/.anticlaudity/ledger.jsonl`), `ANTICLAUDITY_AGY`, `ANTICLAUDITY_CHUNK_TOKENS`, `ANTICLAUDITY_JOBS`, `ANTICLAUDITY_READ_FRACTION`.

## What to delegate

| Delegate | Keep with Claude |
|---|---|
| Summarizing large docs, specs, logs | Writing or changing real code |
| Repo-wide "where is X used?" scans | Debugging non-obvious bugs |
| Extracting lists/tables/API surfaces from long files | Architecture and design decisions |
| Boilerplate, docstrings, format conversion | Security-sensitive review |
| Triaging long CI/test output | Inputs under ~5k tokens |

## Measuring the savings

Every call is logged to the ledger. `anticlaudity stats [--days N] [--json]` reports:

- **Claude tokens kept out of your context**, as two numbers:
  - *likely*: assumes Claude would have read about half of the scope (it usually greps and narrows first). Tune with `ANTICLAUDITY_READ_FRACTION`.
  - *upper bound*: assumes Claude would have read all of it.
  - Both subtract the size of the result Claude receives. Files that were not covered (partial or failed calls) count as zero.
- Source handed to Antigravity, result size, and the compression ratio.
- Antigravity-side tokens spent, including how much went on failed calls.
- Success rate, failures grouped by cause, retries and splits, median wall time, and calls too small to be worth delegating.
- Saved tokens per day.

These are **estimates** (about 4 bytes per token on the files handed over), not a measurement of your Claude bill.

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
