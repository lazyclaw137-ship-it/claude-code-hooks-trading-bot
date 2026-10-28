import base64, json, pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ed25519, padding
import broker, bot
from broker import signing_message, sign, Kalshi
from risk import Risk, RiskError

L = {"max_contracts_per_order": 1, "max_open_exposure_usd": 5,
     "max_daily_loss_usd": 2, "max_orders_per_minute": 3}


class Resp:
    def __init__(self, data, code=200): self.d, self.status_code = data, code
    def json(self): return self.d
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(self.status_code)


class Fake:
    """Routes (method, path) to canned JSON; records calls."""
    def __init__(self, routes): self.routes, self.calls = routes, []
    def request(self, method, url, params=None, json=None, headers=None, **kw):
        path = url.split("/trade-api/v2")[1]
        self.calls.append((method, path, params, json, headers))
        v = self.routes.get((method, path))
        if isinstance(v, Exception): raise v
        if callable(v): v = v()
        return Resp(v if v is not None else {}, 204 if v is None else 200)


def keyed(routes):
    return Kalshi(session=Fake(routes), key=ed25519.Ed25519PrivateKey.generate(),
                  key_id="test")


MKT = {"market": {"status": "active", "yes_ask_dollars": "0.1300",
                  "yes_ask_size_fp": "100.00"}}
CFG = {"ticker": "T", "max_price": 0.15}


def test_signing_message():
    assert signing_message(1, "get", broker.BASE + "/portfolio/orders?x=1") \
        == b"1GET/trade-api/v2/portfolio/orders"


def test_rsa_and_ed25519_verify():
    msg = b"1POST/trade-api/v2/portfolio/events/orders"
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    k.public_key().verify(base64.b64decode(sign(k, msg)), msg,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())
    e = ed25519.Ed25519PrivateKey.generate()
    e.public_key().verify(base64.b64decode(sign(e, msg)), msg)


def test_signed_headers_verify():
    e = ed25519.Ed25519PrivateKey.generate()
    f = Fake({})
    Kalshi(session=f, key=e, key_id="id").signed("DELETE", "/portfolio/events/orders")
    h = f.calls[0][4]
    e.public_key().verify(base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"]),
        h["KALSHI-ACCESS-TIMESTAMP"].encode() + b"DELETE/trade-api/v2/portfolio/events/orders")


def test_basic_rules(tmp_path, monkeypatch):
    monkeypatch.delenv("KALSHI_API_KEY_ID", raising=False)
    t = [0.0]
    r = Risk(L, Kalshi(session=Fake({})), root=str(tmp_path), clock=lambda: t[0])
    with pytest.raises(RiskError): r.check(2, 0.1)
    for i in range(3): r.check(1, 0.1); r.record(f"T{i}", 1, 0.1)
    with pytest.raises(RiskError, match="per_minute"): r.check(1, 0.1)
    # restart: a new Risk object reads the same state
    r2 = Risk(L, Kalshi(session=Fake({})), root=str(tmp_path), clock=lambda: t[0])
    with pytest.raises(RiskError, match="per_minute"): r2.check(1, 0.1)
    t[0] = 61
    (tmp_path / "KILL").write_text("")
    with pytest.raises(RiskError, match="kill"): r2.check(1, 0.1)


def test_exposure_from_exchange(tmp_path):
    k = keyed({("GET", "/portfolio/orders"): {"orders": [
                  {"yes_price_dollars": "0.4000", "remaining_count_fp": "10.00"}]},
               ("GET", "/portfolio/positions"): {"market_positions": [
                  {"position_fp": "3", "market_exposure_dollars": "0.9000"}]},
               ("GET", "/portfolio/balance"): {"balance": 1000, "portfolio_value": 0}})
    r = Risk(L, k, root=str(tmp_path))
    with pytest.raises(RiskError, match=r"exposure_usd \(now \$4.90\)"):
        r.check(1, 0.13)


def test_daily_loss_from_balance(tmp_path):
    vals = iter([1000, 750])
    k = keyed({("GET", "/portfolio/orders"): {"orders": []},
               ("GET", "/portfolio/positions"): {"market_positions": []},
               ("GET", "/portfolio/balance"):
                   lambda: {"balance": next(vals), "portfolio_value": 0}})
    r = Risk(L, k, root=str(tmp_path))
    r.check(1, 0.1)                      # sets day start at $10.00
    with pytest.raises(RiskError, match="daily_loss"): r.check(1, 0.1)


def test_fail_closed(tmp_path):
    k = keyed({("GET", "/portfolio/orders"): RuntimeError("boom")})
    with pytest.raises(RiskError, match="failing closed"):
        Risk(L, k, root=str(tmp_path)).check(1, 0.1)


def test_one_position_dry_run(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "LOG", str(tmp_path / "d.jsonl"))
    k = Kalshi(session=Fake({("GET", "/markets/T"): MKT}))
    r = Risk(L, k, root=str(tmp_path))
    for _ in range(3): bot.step(k, r, CFG)
    d = [json.loads(l)["decision"] for l in open(tmp_path / "d.jsonl")]
    assert d == ["dry_run", "holding", "holding"]


def test_one_position_live(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "LOG", str(tmp_path / "d.jsonl"))
    k = keyed({("GET", "/markets/T"): MKT,
               ("GET", "/portfolio/orders"): {"orders": [{"x": 1}]}})
    bot.step(k, Risk(L, k, root=str(tmp_path)), CFG)
    assert [c[0] for c in k.s.calls].count("POST") == 0
    assert json.loads(open(tmp_path / "d.jsonl").read())["decision"] == "holding"


def test_closed_market_skips(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "LOG", str(tmp_path / "d.jsonl"))
    k = Kalshi(session=Fake({("GET", "/markets/T"):
        {"market": {**MKT["market"], "status": "closed"}}}))
    bot.step(k, Risk(L, k, root=str(tmp_path)), CFG)
    assert "closed" in open(tmp_path / "d.jsonl").read()
