"""Quote history — persisted to quote_history.json in project root."""
import json
import os
import uuid
from datetime import datetime
from typing import List, Dict

LIMIT = 100


class QuoteHistory:
    def __init__(self, path: str):
        self.path = path
        self.entries: List[Dict] = []
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    self.entries = json.load(f)
                # Back-fill id for old entries that lack one
                changed = False
                for e in self.entries:
                    if "id" not in e:
                        e["id"] = uuid.uuid4().hex
                        changed = True
                if changed:
                    self._save()
            except Exception:
                self.entries = []

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self.entries[-LIMIT:], f, indent=2)

    def add(self, customer: str, items: List[Dict], total: float) -> Dict:
        entry = {
            "id":        uuid.uuid4().hex,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "customer":  customer or "Unknown",
            "items":     items,
            "total":     total,
        }
        self.entries.append(entry)
        self._save()
        return entry

    def rename(self, id_: str, name: str) -> bool:
        for e in self.entries:
            if e.get("id") == id_:
                e["customer"] = name
                self._save()
                return True
        return False

    def delete(self, id_: str) -> bool:
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.get("id") != id_]
        if len(self.entries) < before:
            self._save()
            return True
        return False

    def get_all(self) -> List[Dict]:
        return list(reversed(self.entries))
