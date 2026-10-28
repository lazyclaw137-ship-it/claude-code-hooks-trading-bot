#!/usr/bin/env python3
"""BotCookery PreToolUse guard. Claude Code format; also runs when Cursor
or Grok Build load .claude/settings.json, and as a Codex PreToolUse hook.
Exit 0 = no objection (normal permissions still apply).
Exit 2 = block; stderr goes to the agent. Bad input also exits 2."""
import json, re, sys

# .env, .env.local, *.pem, *.key, SSH keys. .env.example is allowed.
SECRET = re.compile(r"(^|[/\s'\"=])(\.env(?!\.example)(\.[\w-]+)?|[\w.-]+\.pem"
                    r"|[\w.-]+\.key|id_rsa|id_ed25519)($|[\s'\";|&)])", re.I)
READ_ONLY_TOOLS = {"read", "read_file", "grep", "glob", "ls", "list_dir"}


def block(msg):
    print(f"BotCookery guard: {msg}", file=sys.stderr)
    sys.exit(2)


try:
    data = json.load(sys.stdin)
    # Claude, Codex and Cursor send tool_name/tool_input. Grok sends
    # toolName/toolInput. Cursor names Bash "Shell"; Grok names it
    # run_terminal_command. So check the input fields, not the name.
    tool = str(data.get("tool_name") or data.get("toolName") or "").lower()
    inp = data.get("tool_input") or data.get("toolInput") or {}
    if isinstance(inp, str):
        inp = json.loads(inp)
    cmd = inp.get("command") or ""
    path = inp.get("file_path") or inp.get("path") or ""
except Exception as exc:
    block(f"could not read the hook input ({exc.__class__.__name__}).")

if cmd:
    if re.search(r"--live\b|BOT_MODE=live|KALSHI_ENV=prod", cmd):
        block("live trading is started by a human in their own terminal, "
              "never by the agent.")
    if SECRET.search(cmd):
        block("commands that touch .env or key files are blocked. "
              "The bot loads secrets from env vars itself.")
    if (re.search(r"(^|[;&|]\s*)(printenv\b|env(\s*$|\s*[|;&>]))", cmd)
            or re.search(r"echo\s+[\"']?\$\{?\w*(KEY|SECRET|TOKEN|PASS)",
                         cmd, re.I)):
        block("printing environment secrets is blocked.")
    if re.search(r"\bgit(\s+-C\s+\S+|\s+-c\s+\S+|\s+--?[\w-]+)*\s+push\b", cmd):
        block("git push needs a human.")
    if "limits.json" in cmd and not re.match(r"\s*(cat|less|head|jq)\s", cmd):
        block("limits.json is human-edited only. Ask the user to change it.")
if path:
    if SECRET.search(" " + path):
        block(f"access to {path} is blocked.")
    if tool not in READ_ONLY_TOOLS and re.search(r"(^|/)limits\.json$", path):
        block("limits.json is human-edited only. Ask the user to change it.")
sys.exit(0)
