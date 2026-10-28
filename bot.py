import json, os, time, uuid, tomllib
from broker import Kalshi
from risk import Risk, RiskError, load_limits, ROOT

LOG = os.path.join(ROOT, "logs", "decisions.jsonl")


def log(d):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    d = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **d}
    with open(LOG, "a") as f:
        f.write(json.dumps(d) + "\n")
    print(json.dumps(d), flush=True)


def holding(k, risk, ticker):
    if k.dry_run:
        return any(o["ticker"] == ticker
                   for o in risk.state.get("paper.json", []))
    if k.resting(ticker):
        return True
    return any(float(p.get("position_fp") or 0) != 0
               for p in k.positions(ticker))


def step(k, risk, cfg):
    t = cfg["ticker"]
    m = k.market(t)
    if m.get("status") != "active":
        return log({"decision": "skip", "why": f"market {m.get('status')}"})
    ask, size = float(m["yes_ask_dollars"]), float(m["yes_ask_size_fp"])
    if not (0 < ask <= cfg["max_price"] and size >= 1):
        return log({"decision": "skip", "ask": ask, "size": size})
    try:
        if holding(k, risk, t):
            return log({"decision": "holding", "ask": ask})
        info = risk.check(1, ask)
    except RiskError as e:
        return log({"decision": "blocked", "reason": str(e), "ask": ask})
    except Exception as e:
        return log({"decision": "blocked",
                    "reason": f"check failed, failing closed: {e}"})
    body = {"ticker": t, "side": "bid", "count": "1.00",
            "price": f"{ask:.4f}", "client_order_id": str(uuid.uuid4()),
            "time_in_force": "good_till_canceled",
            "self_trade_prevention_type": "taker_at_cross"}
    if k.dry_run:
        log({"decision": "dry_run", "body": body, **info})
    else:
        r = k.signed("POST", "/portfolio/events/orders", json=body)
        log({"decision": "sent", "body": body, "resp": r, **info})
    risk.record(t, 1, ask)


def main():
    cfg = tomllib.load(open(os.path.join(ROOT, "config.toml"), "rb"))
    k = Kalshi()
    risk = Risk(load_limits(), k)
    loops, n = int(os.getenv("LOOPS", "0")), 0
    while True:
        try:
            step(k, risk, cfg)
        except Exception as e:
            log({"decision": "error", "error": str(e)})
        n += 1
        if loops and n >= loops:
            break
        time.sleep(cfg["interval_seconds"])


if __name__ == "__main__":
    main()
