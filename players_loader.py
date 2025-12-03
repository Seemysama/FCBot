"""Download and normalize the official EA players database.

Outputs a local JSON (clean_players.json) with normalized names mapped to
player metadata (ids, rating, position). Provides a helper to search by
name and return maskedDefId/baseId values usable by the worker.
"""

import csv
import json
import os
import re
from typing import Dict, List

import requests

EA_DB_URL = os.environ.get(
    "EA_DB_URL",
    "https://content.ea.com/fc24/ultimate-team/players.json",
)
OUTPUT_DB = os.environ.get("EA_OUTPUT_DB", "clean_players.json")


def normalize_name(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[àáâãäå]", "a", name)
    name = re.sub(r"[èéêë]", "e", name)
    name = re.sub(r"[ìíîï]", "i", name)
    name = re.sub(r"[òóôõö]", "o", name)
    name = re.sub(r"[ùúûü]", "u", name)
    name = re.sub(r"[^a-z0-9\s]", "", name)
    return " ".join(name.split())


def _load_source() -> List[dict]:
    """Loads raw player data from HTTP JSON, local JSON or CSV."""
    source = EA_DB_URL
    if source.startswith("http"):
        print(f"[DOWNLOAD] Fetching players DB from {source}...")
        with requests.get(source, timeout=60) as resp:
            resp.raise_for_status()
            return resp.json()

    # Local file
    if not os.path.exists(source):
        raise FileNotFoundError(f"Source {source} not found")

    if source.lower().endswith(".json"):
        print(f"[LOAD] Reading local JSON {source}...")
        with open(source, "r", encoding="utf-8") as f:
            return json.load(f)

    if source.lower().endswith(".csv"):
        print(f"[LOAD] Reading local CSV {source}...")
        with open(source, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    raise ValueError(f"Unsupported source format for {source}")


def fetch_and_process() -> Dict[str, List[dict]]:
    raw_data = _load_source()

    print(f"[PROCESS] Processing {len(raw_data)} players...")
    processed: Dict[str, List[dict]] = {}

    for p in raw_data:
        # Handle both EA JSON fields and CSV columns (FC26 dump)
        masked_def_id = (
            p.get("id")
            or p.get("defId")
            or p.get("assetId")
            or p.get("resourceId")
            or p.get("player_id")
        )
        resource_id = (
            p.get("assetId")
            or p.get("resourceId")
            or p.get("id")
            or p.get("player_id")
        )
        base_id = p.get("baseId") or p.get("baseid") or p.get("player_id")
        rating = p.get("r") or p.get("rating") or p.get("overall")
        position = p.get("p") or p.get("position") or p.get("player_positions")

        full_name = (
            p.get("c")
            or p.get("long_name")
            or p.get("short_name")
            or f"{p.get('f', '').strip()} {p.get('l', '').strip()}"
        ).strip()
        if not full_name:
            continue

        search_key = normalize_name(full_name)
        entry = {
            "name": full_name,
            "maskedDefId": int(masked_def_id) if masked_def_id and str(masked_def_id).isdigit() else masked_def_id,
            "resourceId": int(resource_id) if resource_id and str(resource_id).isdigit() else resource_id,
            "baseId": int(base_id) if base_id and str(base_id).isdigit() else base_id,
            "rating": int(rating) if rating and str(rating).isdigit() else rating,
            "position": position,
        }

        processed.setdefault(search_key, []).append(entry)

    with open(OUTPUT_DB, "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False)

    print(f"[SUCCESS] Wrote {len(processed)} unique keys to {OUTPUT_DB}")
    return processed


def load_db() -> Dict[str, List[dict]]:
    if not os.path.exists(OUTPUT_DB):
        return fetch_and_process()
    with open(OUTPUT_DB, "r", encoding="utf-8") as f:
        return json.load(f)


def find_players(query: str, limit: int = 5) -> List[dict]:
    db = load_db()
    key = normalize_name(query)
    matches: List[dict] = []

    for search_key, entries in db.items():
        if key in search_key:
            matches.extend(entries)

    matches.sort(key=lambda x: x.get("rating") or 0, reverse=True)
    return matches[:limit]


if __name__ == "__main__":
    # Basic CLI helpers
    import argparse

    parser = argparse.ArgumentParser(description="EA Players DB loader/search")
    parser.add_argument("name", nargs="?", help="Player name to search")
    parser.add_argument("--refresh", action="store_true", help="Force download DB")
    args = parser.parse_args()

    if args.refresh:
        fetch_and_process()

    if args.name:
        results = find_players(args.name)
        print(json.dumps(results, indent=2))
