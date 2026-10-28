from broker import Kalshi

k, cur, rows, pages = Kalshi(), None, [], 0
while True:
    p = {"status": "open", "mve_filter": "exclude", "limit": 1000}
    if cur: p["cursor"] = cur
    d = k.public("/markets", params=p)
    pages += 1
    for m in d.get("markets", []):
        ask = float(m.get("yes_ask_dollars") or 0)
        if 0 < ask < 1:
            rows.append((m["close_time"], m["ticker"], ask,
                         m.get("yes_ask_size_fp"), m.get("yes_bid_dollars"),
                         m.get("title", "")[:50]))
    cur = d.get("cursor")
    if not cur:
        break
print(f"{pages} pages, {len(rows)} markets with an ask")
for r in sorted(rows):
    print(*r, sep="  ")
