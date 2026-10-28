import json, os, subprocess, sys
import pytest

GUARD = os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks",
                     "bot_guard.py")


def run(payload):
    data = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, GUARD], input=data,
                          capture_output=True, text=True).returncode


def shapes(cmd=None, path=None, read=False):
    """The same call as Claude Code, Cursor and Grok Build send it."""
    if cmd is not None:
        names = ("Bash", "Shell", "run_terminal_command")
        inp = {"command": cmd}
    else:
        names = ("Read", "Read", "read_file") if read else \
                ("Edit", "Write", "search_replace")
        inp = {"file_path": path}
    return [{"tool_name": names[0], "tool_input": inp},
            {"tool_name": names[1], "tool_input": inp},
            {"toolName": names[2], "toolInput": {"path": path} if path
             else inp}]


BLOCK = ["python bot.py --live", "BOT_MODE=live python bot.py",
         "KALSHI_ENV=prod python bot.py", "cat .env", "cat .env.local",
         "cat ~/.kalshi/kalshi.pem", "printenv", "printenv KALSHI_API_KEY_ID",
         "env | grep KALSHI", "echo $KALSHI_API_KEY_ID",
         "git push origin main", "git -C . push",
         "sed -i s/5/50/ limits.json"]
ALLOW = ["python bot.py", "python bot.py --paper", "pytest -q",
         "cat .env.example", "cat limits.json", "git status",
         'git commit -m "push fix"']


@pytest.mark.parametrize("cmd", BLOCK)
def test_blocks_commands(cmd):
    assert [run(p) for p in shapes(cmd=cmd)] == [2, 2, 2]


@pytest.mark.parametrize("cmd", ALLOW)
def test_allows_commands(cmd):
    assert [run(p) for p in shapes(cmd=cmd)] == [0, 0, 0]


@pytest.mark.parametrize("path", ["/p/.env", "/p/.env.local",
                                  "/p/keys/kalshi.pem", ".env"])
def test_blocks_secret_reads(path):
    assert [run(p) for p in shapes(path=path, read=True)] == [2, 2, 2]


def test_limits_json_read_ok_edit_blocked():
    assert [run(p) for p in shapes(path="/p/limits.json", read=True)] \
        == [0, 0, 0]
    assert [run(p) for p in shapes(path="/p/limits.json")] == [2, 2, 2]


def test_risk_edit_allowed():
    assert [run(p) for p in shapes(path="/p/risk.py")] == [0, 0, 0]


def test_bad_input_fails_closed():
    assert run("not json") == 2
