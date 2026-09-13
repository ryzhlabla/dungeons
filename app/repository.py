import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from .engine import State


class Repository:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS saves (user_id INTEGER PRIMARY KEY, snapshot TEXT NOT NULL)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def get(self, user_id):
        with self.connect() as db:
            row = db.execute("SELECT snapshot FROM saves WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return State()
        data = json.loads(row[0])
        if data.get("content_version") not in {"0.1.0", "0.2.0", "0.3.0", "0.4.0", "0.5.0", "0.6.0", "0.7.0", "0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0"}:
            raise ValueError("Unsupported save version; preserve data and migrate before loading")
        # Additive migration: preserve all existing items, locations, turns and history.
        data["content_version"] = "0.12.0"
        data.setdefault("flags", {})
        data["item_locations"].setdefault("keys", "inside_house")
        data["item_locations"].setdefault("cage", "debris_grotto")
        data["item_locations"].setdefault("bird", "bird_grotto")
        data["item_locations"].setdefault("silver", "silver_grotto")
        return State(**data)

    def save(self, user_id, state):
        with self.connect() as db:
            db.execute("INSERT INTO saves VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET snapshot=excluded.snapshot",
                       (user_id, json.dumps(asdict(state), ensure_ascii=False)))
