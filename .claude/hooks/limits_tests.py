#!/usr/bin/env python3
"""BotCookery PostToolUse hook: after the agent edits risk, limit or
kill-switch code, run the tests. Exit 2 sends the failure to the agent.
Set LIMIT_TESTS to a test file to run just that file (default: tests/)."""
import json, os, re, subprocess, sys

data = json.load(sys.stdin)
inp = data.get("tool_input") or data.get("toolInput") or {}
path = inp.get("file_path") or inp.get("path") or ""
if not path:  # Codex apply_patch puts the patch text in "command"
    m = re.search(r"\*\*\* (?:Update|Add) File: (\S+)", inp.get("command", ""))
    path = m.group(1) if m else ""
if not re.search(r"(risk|limit|kill)[\w-]*\.py$", path):
    sys.exit(0)
root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
target = os.environ.get("LIMIT_TESTS", "tests")
r = subprocess.run([sys.executable, "-m", "pytest", "-q", target],
                   cwd=root, capture_output=True, text=True, timeout=110)
if r.returncode in (4, 5):  # path missing / no tests collected
    print(f"No tests ran for {target} after editing {path}. "
          "Add a limit test or set LIMIT_TESTS.", file=sys.stderr)
    sys.exit(2)
if r.returncode != 0:
    out = (r.stdout + r.stderr)[-3000:]
    print(f"Tests failed after editing {path}:\n{out}", file=sys.stderr)
    sys.exit(2)
sys.exit(0)
