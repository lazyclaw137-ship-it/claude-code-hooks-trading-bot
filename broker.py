"""Kalshi DEMO client. Demo base URL is hardcoded on purpose."""
import base64, os, time
from urllib.parse import urlsplit
import requests

BASE = "https://external-api.demo.kalshi.co/trade-api/v2"


def signing_message(ts_ms, method, url_or_path):
    path = urlsplit(url_or_path).path
    if not path.startswith("/trade-api/v2"):
        path = "/trade-api/v2" + path
    return f"{ts_ms}{method.upper()}{path}".encode()


def load_key(path):
    from cryptography.hazmat.primitives import serialization
    with open(os.path.expanduser(path), "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def sign(key, msg):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa, ed25519
    if isinstance(key, ed25519.Ed25519PrivateKey):
        sig = key.sign(msg)
    elif isinstance(key, rsa.RSAPrivateKey):
        sig = key.sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                       salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())
    else:
        raise ValueError("unsupported key type (need RSA or Ed25519)")
    return base64.b64encode(sig).decode()


class Kalshi:
    def __init__(self, session=None, key=None, key_id=None):
        self.s = session or requests.Session()
        self.key_id = key_id or os.getenv("KALSHI_API_KEY_ID") or None
        kp = os.getenv("KALSHI_PRIVATE_KEY_PATH") or None
        self.key = key or (load_key(kp) if (self.key_id and kp) else None)

    @property
    def dry_run(self):
        return self.key is None

    def public(self, path, params=None):
        r = self.s.request("GET", BASE + path, params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    def signed(self, method, path, params=None, json=None):
        ts = str(int(time.time() * 1000))
        h = {"KALSHI-ACCESS-KEY": self.key_id,
             "KALSHI-ACCESS-TIMESTAMP": ts,
             "KALSHI-ACCESS-SIGNATURE":
                 sign(self.key, signing_message(ts, method, BASE + path))}
        r = self.s.request(method, BASE + path, params=params, json=json,
                           headers=h, timeout=10)
        r.raise_for_status()
        return r.json() if r.status_code != 204 else {}

    def market(self, ticker):
        return self.public(f"/markets/{ticker}")["market"]

    def resting(self, ticker):
        return self.signed("GET", "/portfolio/orders",
                           params={"ticker": ticker, "status": "resting"}
                           ).get("orders", [])

    def positions(self, ticker=None):
        p = {"ticker": ticker} if ticker else {}
        return self.signed("GET", "/portfolio/positions",
                           params=p).get("market_positions", [])

    def all_resting(self):
        out, cur = [], None
        while True:
            p = {"status": "resting", "limit": 1000}
            if cur: p["cursor"] = cur
            d = self.signed("GET", "/portfolio/orders", params=p)
            out += d.get("orders", [])
            cur = d.get("cursor")
            if not cur: return out

    def balance_cents(self):
        b = self.signed("GET", "/portfolio/balance")
        return int(b["balance"]) + int(b["portfolio_value"])
