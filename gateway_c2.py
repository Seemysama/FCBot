"""
GATEWAY C2 - Centre de Commande
FastAPI backend pour piloter le bot depuis React
"""

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import os
import time
from typing import List, Optional

app = FastAPI(title="FUT C2 Gateway")

# CORS : React (5173) -> Python (8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- PATHS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "bot_config.json")
TARGETS_FILE = os.path.join(BASE_DIR, "active_targets.json")
STATS_FILE = os.path.join(BASE_DIR, "snipe_stats.json")
FILTERS_FILE = os.path.join(BASE_DIR, "snipe_filters.json")

# --- MODELS ---
class BotConfig(BaseModel):
    snipeMode: str  # 'safe' | 'aggressive'
    minDelay: float
    maxDelay: float
    maxBuyPrice: int
    pauseOnBuy: int
    softBanThreshold: Optional[int] = 3
    autoSellMarkup: Optional[int] = 30

class SnipeFilter(BaseModel):
    name: str
    params: dict
    expected_min_value: int
    active: bool = True

# --- HELPERS ---
def load_json(filepath, default=None):
    if not os.path.exists(filepath):
        return default if default is not None else {}
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return default if default is not None else {}

def save_json(filepath, data):
    temp_file = f"{filepath}.tmp"
    with open(temp_file, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(temp_file, filepath)

# --- ROUTES ---

@app.get("/health")
def health_check():
    return {"status": "ONLINE", "timestamp": time.time()}

@app.get("/config")
def get_config():
    defaults = {
        "snipeMode": "safe",
        "minDelay": 1.5,
        "maxDelay": 2.5,
        "maxBuyPrice": 10000,
        "pauseOnBuy": 60,
        "softBanThreshold": 3,
        "autoSellMarkup": 30
    }
    return load_json(CONFIG_FILE, defaults)

@app.post("/config")
def update_config(config: BotConfig):
    print(f"[GATEWAY] CONFIG UPDATE: {config.dict()}")
    save_json(CONFIG_FILE, config.dict())
    return {"status": "SUCCESS", "msg": "Configuration appliquée"}

@app.get("/filters")
def get_filters():
    return load_json(FILTERS_FILE, {"filters": []})

@app.post("/filters")
def update_filters(filters: List[SnipeFilter]):
    print(f"[GATEWAY] FILTERS UPDATE: {len(filters)} filtres")
    save_json(FILTERS_FILE, {"filters": [f.dict() for f in filters]})
    return {"status": "SUCCESS", "msg": f"{len(filters)} filtres sauvegardés"}

@app.get("/targets")
def get_targets():
    return load_json(TARGETS_FILE, [])

@app.get("/stats")
def get_stats():
    return load_json(STATS_FILE, {
        "scans": 0,
        "hits": 0,
        "buys": 0,
        "fails": 0,
        "profit_estimate": 0
    })

if __name__ == "__main__":
    print("="*50)
    print("   GATEWAY C2 - Port 8000")
    print("="*50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
