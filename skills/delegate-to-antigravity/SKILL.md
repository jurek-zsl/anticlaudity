---
name: delegate-to-antigravity
description: Offload bulk reading and mechanical work (large docs, repo-wide scans, long logs, boilerplate) to the Antigravity CLI via `anticlaudity` to save Claude context and usage limits. Use when the input to read is large (roughly >20k tokens / many files) and the answer is short, or the work is mechanical. Not for reasoning, debugging, design, or small inputs.
---

# Delegate to Antigravity

`anticlaudity` runs `agy -p` (Gemini Flash by default, read-only) and returns a compact JSON result, so large source material never enters this conversation's context.

## Delegate when ALL are true
- The input is big (a long doc/spec/log, or a repo-wide search across many files; roughly >20k tokens, ~80KB+) **or** the work is mechanical (docstrings, boilerplate, format conversion, renames).
- The answer is short or verifiable (a summary, a list of `file:line` locations, extracted data).
- Being slightly wrong is recoverable, because you will spot-check.

Good examples: "summarize this 200-page spec", "list every place auth errors are handled", "extract all API endpoints from these docs", "which tests failed and why in this 5k-line CI log", "first-pass research of this library's docs".

## Do NOT delegate
- Inputs under ~5k tokens: agy has ~20s and ~18k tokens of fixed overhead, and the call costs more than reading directly.
- Writing or changing real code, debugging non-obvious bugs, architecture or design decisions, security-sensitive review.
- Anything where you would need to re-read the source to trust the answer, because that defeats the point.

## How to call
```bash
anticlaudity "<precise task>" --path <file-or-dir> [--path ...]
```
- Always pass `--path` so scope is bounded (and the ledger can measure savings).
- Make the task specific and say what output you want (e.g. "list with file:line", "max 10 bullets").
- Optional: `--model gemini-3.8-flash-high` for harder reading, `--effort high`, `--timeout 600`.
- Edits are opt-in: `--write` lets agy modify files. Use only for clearly mechanical changes, then review `git diff`.
- Output JSON: `status`, `summary`, `findings[{path,line,note}]`, `confidence`, optional `caveats`. On failure `status` is `error`.

## After the call (required)
1. If `status` is `error` or `confidence` is `low`, or `caveats` mention incomplete coverage: do the work yourself or retry narrower. Do not present it as reliable.
2. Spot-check 1-2 of the cited `file:line` findings against the real files (read just those lines, not the whole source). If any is wrong, distrust the rest.
3. Tell the user briefly that the result came from a delegated Antigravity run, and note any caveats.
4. Never base security-, money-, or data-loss-relevant decisions on an unverified delegated result.

## Measuring
`anticlaudity stats` summarizes the ledger (`~/.anticlaudity/ledger.jsonl`): scope handed off, result size returned, Antigravity tokens spent, low-confidence and too-small calls. Run it when the user asks whether delegation is paying off.
