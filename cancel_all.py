import sys
from broker import Kalshi

k = Kalshi()
if k.dry_run:
    print("No Kalshi credentials set (KALSHI_API_KEY_ID / "
          "KALSHI_PRIVATE_KEY_PATH). Nothing was sent.")
    sys.exit(1)
k.signed("DELETE", "/portfolio/events/orders")
print("cancel-all sent to Kalshi demo")
