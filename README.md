# Claude Code hooks for trading bots (guard + limits tests)

Starter code for the BotCookery recipe **[claude-code-hooks-trading-bots](https://botcookery.com/recipes/claude-code-hooks-trading-bots/)**. The recipe page has the step-by-step guide, the prompt, the findings and the safety notes; this repo is the code that came out of it.

## What it is

Two hook scripts for AI coding agents working on a trading bot, plus the small paper bot they were tested on:

- `.claude/hooks/bot_guard.py`: a PreToolUse hook that blocks reads of key files, `git push`, and edits that weaken the live-trading gate. It accepts Claude Code, Cursor, Grok Build and Codex input shapes and fails closed on bad input.
- `.claude/hooks/limits_tests.py`: a PostToolUse hook that reruns the risk-limit tests after an edit to the risk code and blocks on failure.
- `.claude/settings.json`: the deny rules and hook wiring for Claude Code.

`tests/test_hooks.py` drives the guard with sample inputs in each tool's format.

## What was actually tested

- Mode: **mock (sample hook inputs, no live data)**
- Date: 2026-10-25
- Limits: Both hook scripts run with sample inputs in each tool's documented format, plus a real pytest run on a paper bot; not run inside a live agent session. Quoting tricks and python -c reading os.environ still get past the guard.

The recipe page has the full findings, dated sample output and the prompt this code came from. The code was written by an AI coding assistant from that prompt, then run as described above. Market tickers and slugs in the config were live when it was tested and will expire; swap in current ones.

## Setup

Python 3.11 or newer.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

## Run it (no money)

Try the guard by hand:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}' | python3 .claude/hooks/bot_guard.py; echo "exit=$?"   # exit=2, blocked
echo '{"tool_name":"Bash","tool_input":{"command":"ls"}}' | python3 .claude/hooks/bot_guard.py; echo "exit=$?"                   # exit=0
```

The example bot is a dry run when no keys are set (it logs the order it would send). Set `ticker` in `config.toml` to an open Kalshi demo market and run `LOOPS=3 python bot.py` with no keys in the environment. With demo keys set it sends real demo orders, which was not tested.

To use the hooks in your own bot, copy `.claude/` into its root. The recipe page covers the Cursor, Grok Build and Codex wiring.

## Safety notes

- A hook is a guard rail, not a sandbox. Quoting tricks and `python -c` reading `os.environ` still get past the guard; keep keys outside the project folder too.
- Not tested inside a live agent session.
- Keys for the example bot come from env vars (`KALSHI_API_KEY_ID`, `KALSHI_PRIVATE_KEY_PATH`); never commit them.

## Not financial advice

This is example code for learning how these APIs work. It is not financial advice, not a strategy, and not a recommendation to trade anything. The placeholder rules and prices in the config are there to exercise the code, not forecasts. You are responsible for anything you run, especially with real keys or real money.

## License

MIT. See [LICENSE](LICENSE).
