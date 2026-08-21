"""Saved risk-dashboard snapshots -- lets you freeze a moment's positions/
strikes/greeks/EV to disk and reload it later, so the Risk page can still be
worked on (filters, layout, new features) once the market's closed and
TradeSteward/Schwab have nothing live to fetch.

Stored as one JSON file per snapshot under SNAPSHOTS_DIR, named by
timestamp. A snapshot is just the exact result dict a completed
fetch-risk job produced (same shape the frontend already renders), plus a
'saved_at' timestamp and an optional user-given label.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

SNAPSHOTS_DIR = Path(__file__).resolve().parent.parent / "snapshots"

_SAFE_LABEL_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _slugify(label: str) -> str:
    slug = _SAFE_LABEL_RE.sub("-", label.strip()).strip("-")
    return slug[:50] if slug else "snapshot"


def save_snapshot(result: dict[str, Any], label: str = "") -> dict:
    """Write `result` (a completed fetch-risk job's result dict) to a new
    timestamped file. Returns the snapshot's own metadata (id, label,
    saved_at) for the caller to hand back to the frontend."""
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    saved_at = datetime.now().isoformat(timespec="seconds")
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = _slugify(label) if label else "snapshot"
    snapshot_id = f"{ts}-{slug}"
    path = SNAPSHOTS_DIR / f"{snapshot_id}.json"

    payload = {"id": snapshot_id, "label": label, "saved_at": saved_at, "result": result}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"id": snapshot_id, "label": label, "saved_at": saved_at}


def list_snapshots() -> list[dict]:
    """Metadata only (id/label/saved_at), newest first -- doesn't load each
    file's full result, so listing stays cheap even with many snapshots."""
    if not SNAPSHOTS_DIR.exists():
        return []
    out = []
    for path in SNAPSHOTS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append({"id": data.get("id", path.stem), "label": data.get("label", ""), "saved_at": data.get("saved_at", "")})
    out.sort(key=lambda s: s["saved_at"], reverse=True)
    return out


def load_snapshot(snapshot_id: str) -> dict | None:
    """The full result dict for one snapshot, or None if it doesn't exist
    or the id contains anything that isn't a plain filename component
    (defends against path traversal via a crafted id)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", snapshot_id):
        return None
    path = SNAPSHOTS_DIR / f"{snapshot_id}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data.get("result")


def delete_snapshot(snapshot_id: str) -> bool:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", snapshot_id):
        return False
    path = SNAPSHOTS_DIR / f"{snapshot_id}.json"
    if not path.is_file():
        return False
    path.unlink()
    return True
