"""Minimal FastAPI gateway for ingesting worker telemetry.

Endpoints:
- POST /ingest/scan  -> market_snapshots insert (async via background task)
- POST /ingest/trade -> trade_history insert/log
- GET  /health       -> liveness probe
- GET  /scans        -> latest ingested scans (in-memory buffer)
- GET  /trades       -> latest ingested trades (in-memory buffer)

Uses Postgres if DB_DSN/DATABASE_URL is set; otherwise logs to stdout.
"""

import os
import time
from collections import deque
from typing import List, Optional

import psycopg2
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

DB_DSN = os.environ.get("DB_DSN") or os.environ.get("DATABASE_URL")

app = FastAPI(title="FifaQuant Gateway Lite")

# In-memory buffers for front consumption when DB is absent or for quick reads
SCAN_BUFFER: deque = deque(maxlen=200)
TRADE_BUFFER: deque = deque(maxlen=200)


class MarketData(BaseModel):
    worker_id: str
    player_id: str = Field(..., description="EA player id/maskedDefId")
    player_uuid: Optional[str] = Field(None, description="UUID in players table if known")
    price: int
    trade_id: Optional[str] = None
    expires: Optional[int] = None


class TradeLog(BaseModel):
    worker_id: str
    trade_id: str
    action: str  # BUY/BID/SELL
    price: int
    result: str  # SUCCESS/OUTBID/429/etc
    latency_ms: Optional[int] = None
    player_id: Optional[str] = None
    player_uuid: Optional[str] = None


def _is_uuid(value: Optional[str]) -> bool:
    if not value:
        return False
    return len(value) == 36 and value.count("-") == 4


def _insert_market_snapshot(data: MarketData):
    if not DB_DSN:
        print(f"[LOG ONLY] scan {data.worker_id} -> player {data.player_id} price {data.price}")
        SCAN_BUFFER.appendleft(data.model_dump())
        return

    try:
        with psycopg2.connect(DB_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO market_snapshots (time, player_id, lowest_bin, source)
                    VALUES (NOW(), %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        data.player_uuid if _is_uuid(data.player_uuid) else None,
                        data.price,
                        data.worker_id,
                    ),
                )
            conn.commit()
    except Exception as e:
        print(f"[DB ERROR] snapshot: {e}")


def _insert_trade_log(log: TradeLog):
    if not DB_DSN:
        print(
            f"[LOG ONLY] trade {log.worker_id} {log.action} {log.result} "
            f"{log.trade_id} price={log.price} latency={log.latency_ms}"
        )
        TRADE_BUFFER.appendleft(log.model_dump())
        return

    try:
        with psycopg2.connect(DB_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trade_history (account_id, player_id, trade_type, price, timestamp,
                                              execution_time_ms, method)
                    VALUES (NULL, %s, %s, %s, NOW(), %s, %s)
                    """,
                    (
                        log.player_uuid if _is_uuid(log.player_uuid) else None,
                        log.action[:4].upper(),
                        log.price,
                        log.latency_ms or 0,
                        log.result,
                    ),
                )
            conn.commit()
    except Exception as e:
        print(f"[DB ERROR] trade: {e}")


@app.post("/ingest/scan")
async def ingest_scan(data: MarketData, background_tasks: BackgroundTasks):
    background_tasks.add_task(_insert_market_snapshot, data)
    return {"status": "ack"}


@app.post("/ingest/trade")
async def ingest_trade(log: TradeLog, background_tasks: BackgroundTasks):
    background_tasks.add_task(_insert_trade_log, log)
    return {"status": "logged"}


@app.get("/health")
def health():
    return {"status": "up", "timestamp": time.time()}


@app.get("/scans")
def latest_scans(limit: int = 100):
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be positive")
    return list(list(SCAN_BUFFER)[:limit])


@app.get("/trades")
def latest_trades(limit: int = 100):
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be positive")
    return list(list(TRADE_BUFFER)[:limit])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
