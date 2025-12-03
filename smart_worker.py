"""Production-grade market worker with backoff, validation and gateway hooks.

Features:
- Loads validated session from active_session.json (created by auth_manager_v2.py)
- Validates token via /user/massInfo before starting
- Exponential backoff + jitter on 429/5xx
- Deduplicates tradeIds with TTL
- Optional dry-run mode (DRY_RUN=1) to test without EA calls
- Reports scans/trades to a FastAPI gateway (gateway_app.py)
"""

import json
import os
import random
import time
from typing import Dict, List, Optional

import requests

SESSION_FILE = "active_session.json"
# Default FC26 host; override with EA_BASE_URL if needed.
EA_BASE_URL = os.environ.get(
    "EA_BASE_URL",
    "https://utas.mob.v5.prd.futc-ext.gcp.ea.com/ut/game/fc26",
)
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8000")
WORKER_ID = os.environ.get("WORKER_ID", "WORKER-PY-01")
MAX_RETRIES = 5
BACKOFF_BASE = 2
BACKOFF_CAP = 32
MIN_EXPIRES = int(os.environ.get("MIN_EXPIRES", 2))
VALIDATION_PATH = os.environ.get("EA_VALIDATION_PATH", "/user/massInfo")
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
SKIP_VALIDATION = os.environ.get("EA_VALIDATION_SKIP", "0") == "1"

# ========== ANTI-BAN SETTINGS ==========
# Délai entre chaque cycle de recherche (secondes)
CYCLE_DELAY_MIN = float(os.environ.get("CYCLE_DELAY_MIN", "3.0"))
CYCLE_DELAY_MAX = float(os.environ.get("CYCLE_DELAY_MAX", "7.0"))
# Nombre max d'achats par heure (évite les patterns suspects)
MAX_BUYS_PER_HOUR = int(os.environ.get("MAX_BUYS_PER_HOUR", "20"))
# Pause longue après un achat (simule un humain qui vérifie)
POST_BUY_PAUSE_MIN = float(os.environ.get("POST_BUY_PAUSE_MIN", "5.0"))
POST_BUY_PAUSE_MAX = float(os.environ.get("POST_BUY_PAUSE_MAX", "15.0"))
# Pause aléatoire toutes les X recherches (comportement humain)
RANDOM_BREAK_EVERY = int(os.environ.get("RANDOM_BREAK_EVERY", "30"))
RANDOM_BREAK_DURATION = float(os.environ.get("RANDOM_BREAK_DURATION", "30.0"))


class SmartSession:
    def __init__(self):
        self.session = requests.Session()
        self.token: Optional[str] = None
        self.user_agent: Optional[str] = None
        self.load_session()

    def load_session(self):
        if not os.path.exists(SESSION_FILE):
            raise SystemExit("[STOP] Session file missing. Run auth_manager_v2.py first.")

        with open(SESSION_FILE, "r") as f:
            data = json.load(f)

        self.token = data.get("x-ut-sid")
        self.user_agent = data.get("user_agent")

        if not self.token:
            raise SystemExit("[STOP] x-ut-sid missing in session file.")

        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "X-UT-SID": self.token,
                "X-FC-SID": self.token,  # FC26 uses this header name
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )
        print(f"[INIT] Session loaded (token {self.token[:8]}...)")

    def validate(self) -> bool:
        if DRY_RUN:
            print("[INIT] DRY_RUN=1 -> skipping remote validation")
            return True
        if SKIP_VALIDATION:
            print("[INIT] EA_VALIDATION_SKIP=1 -> skipping remote validation")
            return True
        try:
            path = VALIDATION_PATH if VALIDATION_PATH.startswith("/") else f"/{VALIDATION_PATH}"
            resp = self.request("GET", f"{EA_BASE_URL}{path}", critical=True)
            if resp and resp.status_code == 200:
                print("[INIT] Token validated (massInfo ok).")
                return True
        except Exception as e:
            print(f"[INIT] Validation failed: {e}")
        return False

    def request(self, method: str, url: str, critical: bool = False, **kwargs):
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.request(method, url, timeout=5, **kwargs)

                if resp.status_code == 200:
                    return resp

                if resp.status_code == 401:
                    print("[AUTH] Token expired (401). Exit.")
                    raise SystemExit(1)

                if resp.status_code == 429 or resp.status_code >= 500:
                    wait = min(BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 1), BACKOFF_CAP)
                    print(f"[BACKOFF] {resp.status_code} -> sleep {wait:.2f}s")
                    time.sleep(wait)
                    continue

                # Other status codes: return to caller for handling
                return resp
            except requests.exceptions.RequestException as e:
                print(f"[NET] Request error: {e}")
                time.sleep(2)

        if critical:
            raise Exception("Max retries reached on critical request")
        return None


class TradeCache:
    def __init__(self, ttl: int = 300):
        self.ttl = ttl
        self.cache: Dict[str, float] = {}

    def seen(self, trade_id: str) -> bool:
        now = time.time()
        self.cache = {k: v for k, v in self.cache.items() if now - v < self.ttl}
        return trade_id in self.cache

    def add(self, trade_id: str):
        self.cache[trade_id] = time.time()


class MarketLogic:
    def __init__(self, session: SmartSession):
        self.s = session
        self.trades = TradeCache()
        self.buys_this_hour = 0
        self.hour_start = time.time()
        self.search_count = 0

    def _mock_items(self, target_id: int) -> List[dict]:
        trade_id = str(random.randint(1_000_000_000, 9_999_999_999))
        price = random.randint(9000, 16000)
        return [
            {
                "tradeId": trade_id,
                "buyNowPrice": price,
                "expires": random.randint(5, 50),
            }
        ]

    def search(self, player_def_id: int, max_price: int) -> List[dict]:
        if DRY_RUN:
            return self._mock_items(player_def_id)

        params = {
            "type": "player",
            "maskedDefId": player_def_id,
            "maxb": max_price,
            "num": 21,
            "start": 0,
        }
        url = f"{EA_BASE_URL}/transfermarket?_={int(time.time() * 1000)}"
        resp = self.s.request("GET", url, params=params)
        if resp and resp.status_code == 200:
            return resp.json().get("auctionInfo", [])
        return []

    def send_scan_metric(self, player_id: int, item: dict):
        try:
            payload = {
                "worker_id": WORKER_ID,
                "player_id": player_id,
                "price": item.get("buyNowPrice"),
                "trade_id": item.get("tradeId"),
                "expires": item.get("expires"),
            }
            requests.post(f"{GATEWAY_URL}/ingest/scan", json=payload, timeout=0.5)
        except Exception:
            pass

    def send_trade_metric(self, trade_id: str, action: str, result: str, price: int, latency_ms: Optional[int]):
        try:
            payload = {
                "worker_id": WORKER_ID,
                "trade_id": trade_id,
                "action": action,
                "price": price,
                "result": result,
                "latency_ms": latency_ms,
            }
            requests.post(f"{GATEWAY_URL}/ingest/trade", json=payload, timeout=0.5)
        except Exception:
            pass

    def snipe_routine(self, target_id: int, max_buy: int):
        # Reset compteur horaire
        if time.time() - self.hour_start > 3600:
            self.hour_start = time.time()
            self.buys_this_hour = 0
            print("[ANTI-BAN] Reset compteur horaire")

        # Check limite d'achats par heure
        if self.buys_this_hour >= MAX_BUYS_PER_HOUR:
            wait = 3600 - (time.time() - self.hour_start)
            print(f"[ANTI-BAN] Limite {MAX_BUYS_PER_HOUR} achats/h atteinte. Pause {wait:.0f}s")
            time.sleep(max(60, wait))
            return

        # Pause aléatoire périodique (comportement humain)
        self.search_count += 1
        if self.search_count % RANDOM_BREAK_EVERY == 0:
            pause = random.uniform(RANDOM_BREAK_DURATION * 0.5, RANDOM_BREAK_DURATION * 1.5)
            print(f"[ANTI-BAN] Pause humaine de {pause:.1f}s (après {self.search_count} recherches)")
            time.sleep(pause)

        items = self.search(target_id, max_buy)

        for item in items:
            trade_id = str(item.get("tradeId"))
            price = item.get("buyNowPrice") or 0
            expires = item.get("expires") or 0

            self.send_scan_metric(target_id, item)

            if self.trades.seen(trade_id):
                continue
            self.trades.add(trade_id)

            if expires < MIN_EXPIRES:
                print(f"[SKIP] Trade {trade_id} expires too soon ({expires}s)")
                continue

            if price > max_buy:
                continue

            print(f"[OPPORTUNITY] Trade {trade_id} price {price} exp {expires}s")
            bought = self.execute_buy(trade_id, price)
            if bought:
                self.buys_this_hour += 1
                # Pause post-achat (simule vérification humaine)
                pause = random.uniform(POST_BUY_PAUSE_MIN, POST_BUY_PAUSE_MAX)
                print(f"[ANTI-BAN] Pause post-achat {pause:.1f}s ({self.buys_this_hour}/{MAX_BUYS_PER_HOUR} cette heure)")
                time.sleep(pause)

    def execute_buy(self, trade_id: str, price: int) -> bool:
        if DRY_RUN:
            print(f"[$$$][DRY] would bid {price} on {trade_id}")
            self.send_trade_metric(trade_id, "BID", "DRY_RUN", price, None)
            return True

        url = f"{EA_BASE_URL}/trade/{trade_id}/bid"
        payload = {"bid": price}
        headers = {"X-HTTP-Method-Override": "PUT"}

        resp = self.s.request("PUT", url, json=payload, headers=headers)

        if not resp:
            return False

        latency_ms = int(resp.elapsed.total_seconds() * 1000) if resp.elapsed else None

        if resp.status_code == 200:
            print(f"[$$$] BID sent {price} (latency {latency_ms}ms)")
            self.send_trade_metric(trade_id, "BID", "SUCCESS", price, latency_ms)
            return True
        elif resp.status_code == 461:
            print("[FAIL] Outbid/Sold (461)")
            self.send_trade_metric(trade_id, "BID", "OUTBID", price, latency_ms)
        elif resp.status_code == 478:
            print("[FAIL] Invalid trade (478)")
            self.send_trade_metric(trade_id, "BID", "INVALID", price, latency_ms)
        else:
            print(f"[FAIL] Bid failed code {resp.status_code}")
            self.send_trade_metric(trade_id, "BID", f"HTTP_{resp.status_code}", price, latency_ms)
        return False


def main():
    target_id = int(os.environ.get("TARGET_PLAYER_ID", "239085"))
    max_buy = int(os.environ.get("MAX_BUY_PRICE", "15000"))

    session = SmartSession()
    if not session.validate():
        raise SystemExit("[STOP] Token validation failed. Run auth first.")

    bot = MarketLogic(session)
    print(f"[START] Worker {WORKER_ID} targeting {target_id} <= {max_buy} (dry_run={DRY_RUN})")
    print(f"[ANTI-BAN] Délai: {CYCLE_DELAY_MIN}-{CYCLE_DELAY_MAX}s | Max achats/h: {MAX_BUYS_PER_HOUR} | Pause post-achat: {POST_BUY_PAUSE_MIN}-{POST_BUY_PAUSE_MAX}s")

    while True:
        bot.snipe_routine(target_id, max_buy)
        delay = random.uniform(CYCLE_DELAY_MIN, CYCLE_DELAY_MAX)
        time.sleep(delay)


if __name__ == "__main__":
    main()
