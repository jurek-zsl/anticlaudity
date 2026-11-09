"""Offline tests: a stub `agy` stands in for the real Antigravity CLI."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "bin", "anticlaudity")

# Behaviour is steered by markers in the prompt:
#   FAIL      -> status ERROR after burning tokens (like a mid-turn failure)
#   FASTERR   -> immediate ERROR with zero tokens (like a flag conflict)
#   EMPTY     -> SUCCESS but no structured_output and an empty response
#   TEXTJSON  -> SUCCESS, no structured_output, JSON only inside `response`
#   PROSE     -> SUCCESS, no structured_output, plain prose
#   SPLITME   -> EMPTY whenever the scope lists more than 2 files (succeeds once split)
#   SLOW      -> sleeps past the timeout
# Every call appends its argv to $STUB_LOG so tests can inspect flags / call counts.
STUB = r'''#!/usr/bin/env python3
import json, os, sys, time
args = sys.argv[1:]
prompt = args[args.index("-p") + 1]
with open(os.environ["STUB_LOG"], "a") as f:
    f.write(json.dumps(args) + "\n")
scope = prompt.split("SCOPE", 1)[1].split("RULES:", 1)[0]
nfiles = sum(1 for l in scope.splitlines() if l.startswith("- /"))
mode = args[args.index("--mode") + 1]

def out(**kw):
    base = {"status": "SUCCESS", "duration_seconds": 1.0, "response": "",
            "usage": {"total_tokens": 1000}}
    base.update(kw)
    print(json.dumps(base))
    sys.exit(0)

if "SLOW" in prompt:
    time.sleep(60)
if "FASTERR" in prompt:
    out(status="ERROR", usage={"total_tokens": 0})
if "FAIL" in prompt:
    out(status="ERROR", usage={"total_tokens": 500}, response="boom")
if "EMPTY" in prompt or ("SPLITME" in prompt and nfiles > 2):
    out()
good = {"summary": "mode=%s files=%d" % (mode, nfiles), "confidence": "high",
        "findings": [{"path": "/x", "line": 1, "note": "n"}],
        "caveats": "", "changed_files": []}
if "TEXTJSON" in prompt:
    out(response="Here you go:\n```json\n" + json.dumps(good) + "\n```")
if "PROSE" in prompt:
    out(response="I looked at it and it is fine.")
out(structured_output=good)
'''


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.stub = os.path.join(d, "agy")
        with open(self.stub, "w") as f:
            f.write(STUB)
        os.chmod(self.stub, os.stat(self.stub).st_mode | stat.S_IXUSR)
        self.ledger = os.path.join(d, "ledger.jsonl")
        self.log = os.path.join(d, "calls.log")
        self.doc = os.path.join(d, "doc.txt")
        with open(self.doc, "w") as f:
            f.write("hello " * 1000)
        # a project dir with 6 files of ~2.5k tokens each
        self.proj = os.path.join(d, "proj")
        os.makedirs(os.path.join(self.proj, "node_modules"))
        for i in range(6):
            with open(os.path.join(self.proj, "f%d.txt" % i), "w") as f:
                f.write("word " * 2000)
        with open(os.path.join(self.proj, "node_modules", "skip.txt"), "w") as f:
            f.write("x" * 5000)
        with open(os.path.join(self.proj, "img.bin"), "wb") as f:
            f.write(b"\0" * 5000)
        self.env = dict(os.environ, ANTICLAUDITY_AGY=self.stub,
                        ANTICLAUDITY_LEDGER=self.ledger, STUB_LOG=self.log,
                        ANTICLAUDITY_GRACE="1")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run([sys.executable, CLI] + list(args), env=self.env,
                              capture_output=True, text=True, cwd=self.tmp.name)

    def calls(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as f:
            return [json.loads(l) for l in f]

    def ledger_rows(self):
        with open(self.ledger) as f:
            return [json.loads(l) for l in f]

    # ---- basics -----------------------------------------------------------
    def test_read_only_by_default(self):
        p = self.run_cli("summarize", "--path", self.doc)
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout)
        self.assertEqual(out["status"], "ok")
        self.assertIn("mode=plan", out["summary"])
        self.assertNotIn("caveats", out)  # empty fields are dropped
        self.assertNotIn("changed_files", out)
        self.assertNotIn("chunks", out)

    def test_write_flag_switches_mode(self):
        out = json.loads(self.run_cli("edit", "--path", self.doc, "--write").stdout)
        self.assertIn("mode=accept-edits", out["summary"])

    def test_missing_path_is_an_error(self):
        p = self.run_cli("x", "--path", "/definitely/not/here")
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stdout)["status"], "error")

    def test_agy_failure_is_reported_and_logged(self):
        p = self.run_cli("FAIL please", "--path", self.doc)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stdout)["status"], "error")
        self.assertEqual(self.ledger_rows()[0]["status"], "error")

    # ---- the model/effort conflict that broke real calls --------------------
    def test_effort_folds_into_model_suffix(self):
        self.run_cli("t", "--path", self.doc, "--effort", "high")
        argv = self.calls()[0]
        self.assertEqual(argv[argv.index("--model") + 1], "gemini-3.8-flash-high")
        self.assertNotIn("--effort", argv)

    def test_effort_kept_for_unsuffixed_model(self):
        self.run_cli("t", "--path", self.doc, "--model", "claude-sonnet-4-6", "--effort", "high")
        argv = self.calls()[0]
        self.assertEqual(argv[argv.index("--effort") + 1], "high")

    # ---- recovery -----------------------------------------------------------
    def test_json_inside_response_is_recovered(self):
        out = json.loads(self.run_cli("TEXTJSON", "--path", self.doc).stdout)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["confidence"], "high")
        self.assertEqual(len(self.calls()), 1)

    def test_prose_answer_is_kept_as_low_confidence(self):
        out = json.loads(self.run_cli("PROSE", "--path", self.doc).stdout)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["confidence"], "low")
        self.assertIn("it is fine", out["summary"])

    def test_empty_output_is_retried_then_reported(self):
        p = self.run_cli("EMPTY", "--path", self.doc)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(len(self.calls()), 2)  # one retry, single file can't split
        self.assertEqual(self.ledger_rows()[0]["error_kind"], "no_output")

    def test_fast_error_does_not_split(self):
        p = self.run_cli("FASTERR", "--path", self.proj, "--chunk-tokens", "100000")
        self.assertEqual(p.returncode, 1)
        self.assertEqual(len(self.calls()), 2)  # 1 try + 1 retry, no halving
        self.assertEqual(json.loads(p.stdout)["status"], "error")

    def test_timeout_kills_agy_and_is_reported(self):
        p = self.run_cli("SLOW", "--path", self.doc, "--timeout", "1")
        self.assertEqual(p.returncode, 1)
        self.assertEqual(self.ledger_rows()[0]["error_kind"], "timeout")

    # ---- chunking -----------------------------------------------------------
    def test_dry_run_plans_chunks_and_skips_junk(self):
        p = self.run_cli("t", "--path", self.proj, "--chunk-tokens", "6000", "--dry-run")
        plan = json.loads(p.stdout)
        self.assertEqual(plan["files"], 6)  # node_modules and the binary are skipped
        self.assertEqual(plan["chunks"], 3)
        self.assertEqual(self.calls(), [])  # nothing was sent to agy

    def test_big_scope_is_chunked_and_merged(self):
        p = self.run_cli("t", "--path", self.proj, "--chunk-tokens", "6000")
        out = json.loads(p.stdout)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["chunks"], 3)
        self.assertEqual(len(self.calls()), 3)
        self.assertEqual(len(out["findings"]), 3)
        self.assertIn("[1/3]", out["summary"])

    def test_oversized_chunk_is_split_on_failure(self):
        # all 6 files in one chunk: stub returns nothing for >2 files, so the
        # wrapper must halve until it works instead of failing.
        p = self.run_cli("SPLITME", "--path", self.proj, "--chunk-tokens", "100000")
        out = json.loads(p.stdout)
        self.assertEqual(out["status"], "ok", p.stdout)
        self.assertNotIn("uncovered_files", out)
        self.assertGreater(len(self.calls()), 2)
        self.assertGreater(self.ledger_rows()[0]["splits"], 0)

    def test_partial_result_when_one_chunk_dies(self):
        # the stub keys off the prompt, which lists file paths: a FAIL-named file
        # poisons whichever chunk it lands in
        os.rename(os.path.join(self.proj, "f3.txt"), os.path.join(self.proj, "FAIL_f3.txt"))
        p = self.run_cli("t", "--path", self.proj, "--chunk-tokens", "6000")
        out = json.loads(p.stdout)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertEqual(out["status"], "partial")
        self.assertEqual(out["confidence"], "low")
        self.assertTrue(out["uncovered_files"])
        self.assertIn("INCOMPLETE", out["caveats"])

    def test_too_many_chunks_is_refused_up_front(self):
        p = self.run_cli("t", "--path", self.proj, "--chunk-tokens", "3000", "--max-chunks", "2")
        self.assertEqual(p.returncode, 1)
        self.assertIn("scope too large", json.loads(p.stdout)["error"])
        self.assertEqual(self.calls(), [])

    # ---- stats --------------------------------------------------------------
    def test_ledger_and_stats(self):
        out = json.loads(self.run_cli("summarize", "--path", self.proj).stdout)
        self.assertGreater(out["est_claude_tokens_saved"], 0)
        row = self.ledger_rows()[0]
        self.assertEqual(row["status"], "ok")
        self.assertGreater(row["scope_tokens_est"], 0)
        self.assertEqual(row["saved_tokens_est"], out["est_claude_tokens_saved"])
        stats = self.run_cli("stats")
        self.assertEqual(stats.returncode, 0, stats.stderr)
        self.assertIn("1 ok", stats.stdout)
        self.assertIn("kept out of your context", stats.stdout)
        self.assertIn("likely:", stats.stdout)

    def test_stats_json_and_failure_breakdown(self):
        self.run_cli("summarize", "--path", self.proj)
        self.run_cli("EMPTY", "--path", self.doc)
        s = json.loads(self.run_cli("stats", "--json").stdout)
        self.assertEqual((s["ok"], s["failed"]), (1, 1))
        self.assertEqual(s["failures_by_kind"], {"no_output": 1})
        self.assertGreater(s["claude_tokens_saved_upper"], s["claude_tokens_saved_conservative"])

    def test_stats_reads_legacy_ledger_rows(self):
        with open(self.ledger, "w") as f:
            f.write(json.dumps({"ts": "2999-01-01T00:00:00+0000", "status": "ok",
                                "scope_tokens_est": 50000, "result_tokens_est": 500,
                                "wall_seconds": 10}) + "\n")
            f.write(json.dumps({"ts": "2999-01-01T00:00:01+0000", "status": "error",
                                "error": "agy status ERROR: "}) + "\n")
        s = json.loads(self.run_cli("stats", "--json", "--days", "99999").stdout)
        self.assertEqual((s["ok"], s["failed"]), (1, 1))
        self.assertGreater(s["claude_tokens_saved_upper"], 40000)


if __name__ == "__main__":
    unittest.main()
