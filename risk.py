"""Every check runs before every order. Any error here blocks the order."""
import json, os, time

ROOT = os.path.dirname(os.path.abspath(__file__))


class RiskError(Exception):
    pass


def load_limits(path=os.path.join(ROOT, "limits.json")):
    return json.load(open(path))


class State:
    """Small JSON files under state/ so a restart doesn't reset limits."""
    def __init__(self, root=ROOT):
        self.dir = os.path.join(root, "state")
        os.makedirs(self.dir, exist_ok=True)

    def get(self, name, default):
        p = os.path.join(self.dir, name)
        return json.load(open(p)) if os.path.exists(p) else default

    def put(self, name, value):
        p = os.path.join(self.dir, name)
        tmp = p + ".tmp"
        json.dump(value, open(tmp, "w"))
        os.replace(tmp, p)


def kill_active(root=ROOT):
    return os.path.exists(os.path.join(root, "KILL")) or \
        os.getenv("BOT_KILL") == "1"


def exposure_usd(broker, state):
    if broker.dry_run:
        return sum(o["price"] * o["count"] for o in state.get("paper.json", []))
    total = 0.0
    for o in broker.all_resting():
        total += float(o["yes_price_dollars"]) * float(o["remaining_count_fp"])
    for p in broker.positions():
        total += abs(float(p.get("market_exposure_dollars") or 0))
    return total


def daily_loss_usd(broker, state, today=None):
    if broker.dry_run:
        return None
    today = today or time.strftime("%Y-%m-%d")
    now = broker.balance_cents()
    start = state.get("day_start.json", {})
    if start.get("date") != today:
        start = {"date": today, "cents": now}
        state.put("day_start.json", start)
    return max(0, start["cents"] - now) / 100


class Risk:
    def __init__(self, limits, broker, root=ROOT, clock=time.time):
        self.l, self.b, self.root, self.clock = limits, broker, root, clock
        self.state = State(root)

    def check(self, count, price):
        if kill_active(self.root):
            raise RiskError("kill switch on")
        if count > self.l["max_contracts_per_order"]:
            raise RiskError("max_contracts_per_order")
        now = self.clock()
        sent = [t for t in self.state.get("sent.json", []) if now - t < 60]
        if len(sent) >= self.l["max_orders_per_minute"]:
            raise RiskError("max_orders_per_minute")
        try:
            exp = exposure_usd(self.b, self.state)
            loss = daily_loss_usd(self.b, self.state)
        except Exception as e:
            raise RiskError(f"risk data unavailable, failing closed: {e}")
        if exp + price * count > self.l["max_open_exposure_usd"]:
            raise RiskError(f"max_open_exposure_usd (now ${exp:.2f})")
        if loss is not None and loss >= self.l["max_daily_loss_usd"]:
            raise RiskError(f"max_daily_loss_usd (down ${loss:.2f} today)")
        return {"exposure": round(exp, 4),
                "daily_loss": "not tracked in dry run" if loss is None
                else loss}

    def record(self, ticker, count, price):
        now = self.clock()
        sent = [t for t in self.state.get("sent.json", []) if now - t < 60]
        self.state.put("sent.json", sent + [now])
        if self.b.dry_run:
            paper = self.state.get("paper.json", [])
            paper.append({"ticker": ticker, "count": count, "price": price,
                          "ts": now})
            self.state.put("paper.json", paper)
