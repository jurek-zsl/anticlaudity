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

STUB = r'''#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
if "FAIL" in " ".join(args):
    print(json.dumps({"status": "ERROR", "response": "boom"}))
    sys.exit(0)
mode = args[args.index("--mode") + 1]
print(json.dumps({
    "status": "SUCCESS", "duration_seconds": 1.0, "response": "",
    "usage": {"total_tokens": 1234},
    "structured_output": {
        "summary": "mode=" + mode, "confidence": "high",
        "findings": [{"path": "/x", "line": 1, "note": "n"}],
        "caveats": "", "changed_files": [],
    },
}))
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
        self.doc = os.path.join(d, "doc.txt")
        with open(self.doc, "w") as f:
            f.write("hello " * 1000)
        self.env = dict(os.environ, ANTICLAUDITY_AGY=self.stub, ANTICLAUDITY_LEDGER=self.ledger)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run([sys.executable, CLI] + list(args), env=self.env,
                              capture_output=True, text=True, cwd=self.tmp.name)

    def test_read_only_by_default(self):
        p = self.run_cli("summarize", "--path", self.doc)
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["summary"], "mode=plan")
        self.assertNotIn("caveats", out)  # empty fields are dropped
        self.assertNotIn("changed_files", out)

    def test_write_flag_switches_mode(self):
        out = json.loads(self.run_cli("edit", "--path", self.doc, "--write").stdout)
        self.assertEqual(out["summary"], "mode=accept-edits")

    def test_missing_path_is_an_error(self):
        p = self.run_cli("x", "--path", "/definitely/not/here")
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stdout)["status"], "error")

    def test_agy_failure_is_reported_and_logged(self):
        p = self.run_cli("FAIL please", "--path", self.doc)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stdout)["status"], "error")
        with open(self.ledger) as f:
            self.assertEqual(json.loads(f.readline())["status"], "error")

    def test_ledger_and_stats(self):
        self.run_cli("summarize", "--path", self.doc)
        with open(self.ledger) as f:
            row = json.loads(f.readline())
        self.assertEqual(row["status"], "ok")
        self.assertGreater(row["scope_tokens_est"], 0)
        stats = self.run_cli("stats")
        self.assertEqual(stats.returncode, 0, stats.stderr)
        self.assertIn("1 calls (1 ok, 0 failed)", stats.stdout)


if __name__ == "__main__":
    unittest.main()
