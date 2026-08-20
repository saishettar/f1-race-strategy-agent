"""
One-off script: pull a full historical session from OpenF1 and cache it to
disk as JSON so the replay engine never has to hit the network again.

Usage:
    python -m app.ingest 9523
"""
import json
import sys
import time
from pathlib import Path

import httpx

OPENF1_BASE = "https://api.openf1.org/v1"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ENDPOINTS = ["sessions", "drivers", "laps", "stints", "intervals", "pit", "weather", "race_control"]


def fetch_endpoint(client: httpx.Client, endpoint: str, session_key: int, retries: int = 6) -> list:
    for attempt in range(retries):
        resp = client.get(f"{OPENF1_BASE}/{endpoint}", params={"session_key": session_key}, timeout=60)
        if resp.status_code == 429:
            wait = 2 ** attempt  # 1, 2, 4, 8, 16, 32s
            print(f"(rate limited, waiting {wait}s) ", end="", flush=True)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()
    return resp.json()


def ingest_session(session_key: int) -> Path:
    out_dir = DATA_DIR / str(session_key)
    out_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client() as client:
        for endpoint in ENDPOINTS:
            out_path = out_dir / f"{endpoint}.json"
            if out_path.exists():
                print(f"skipping {endpoint} (already cached)")
                continue
            print(f"fetching {endpoint} ...", end=" ", flush=True)
            data = fetch_endpoint(client, endpoint, session_key)
            out_path.write_text(json.dumps(data), encoding="utf-8")
            print(f"{len(data)} records -> {out_path.name}")
            time.sleep(1.0)  # be polite to the free tier

    return out_dir


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m app.ingest <session_key>")
        sys.exit(1)
    session_key = int(sys.argv[1])
    out_dir = ingest_session(session_key)
    print(f"\nDone. Cached to {out_dir}")
