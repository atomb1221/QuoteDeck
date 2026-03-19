"""SQLite database for PocketPricer — customers, prices, quotes."""
import json
import sqlite3
from typing import List, Dict, Optional


def _conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str):
    with _conn(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS customers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    UNIQUE NOT NULL,
                created_at TEXT    DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS customer_prices (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id       INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                tonnage_price     REAL    NOT NULL,
                steel_description TEXT    DEFAULT '',
                quoted_at         TEXT    DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS quotes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
                name        TEXT    NOT NULL,
                total_value REAL    NOT NULL,
                items_count INTEGER NOT NULL,
                quote_data  TEXT    NOT NULL,
                created_at  TEXT    DEFAULT (datetime('now'))
            );
        """)


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        init_db(db_path)
        self._migrate()

    def _migrate(self):
        """Add columns introduced after initial release."""
        with self._conn() as conn:
            try:
                conn.execute("ALTER TABLE customer_prices ADD COLUMN steel_description TEXT DEFAULT ''")
                conn.commit()
            except Exception:
                pass  # column already exists

    def _conn(self):
        return _conn(self.db_path)

    # ── Customers ──────────────────────────────────────────────────────────────

    def search_customers(self, query: str, limit: int = 8) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, name FROM customers WHERE name LIKE ? ORDER BY name LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def find_or_create_customer(self, name: str) -> Dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, name FROM customers WHERE name = ?", (name,)
            ).fetchone()
            if row:
                return dict(row)
            conn.execute("INSERT INTO customers (name) VALUES (?)", (name,))
            conn.commit()
            row = conn.execute(
                "SELECT id, name FROM customers WHERE name = ?", (name,)
            ).fetchone()
            return dict(row)

    def get_customer_quotes(self, customer_id: int, limit: int = 3) -> List[Dict]:
        """Return the last N quotes for a customer, with parsed quote_data."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT id, name, total_value, items_count, quote_data, created_at
                   FROM quotes WHERE customer_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (customer_id, limit),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["quote_data"] = json.loads(d["quote_data"])
            result.append(d)
        return result

    # ── Quotes ────────────────────────────────────────────────────────────────

    def list_quotes(self, limit: int = 100) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT q.id, q.name, q.total_value, q.items_count, q.created_at,
                          c.name AS customer_name
                   FROM quotes q
                   LEFT JOIN customers c ON q.customer_id = c.id
                   ORDER BY q.created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def save_quote(
        self,
        customer_id: Optional[int],
        name: str,
        total_value: float,
        items_count: int,
        quote_data: list,
    ) -> Dict:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO quotes (customer_id, name, total_value, items_count, quote_data)
                   VALUES (?, ?, ?, ?, ?)""",
                (customer_id, name, total_value, items_count, json.dumps(quote_data)),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM quotes WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
        return dict(row)

    def get_quote(self, quote_id: int) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM quotes WHERE id = ?", (quote_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["quote_data"] = json.loads(d["quote_data"])
        return d

    def rename_quote(self, quote_id: int, name: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE quotes SET name = ? WHERE id = ?", (name, quote_id)
            )
            conn.commit()
        return cur.rowcount > 0

    def delete_quote(self, quote_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM quotes WHERE id = ?", (quote_id,))
            conn.commit()
        return cur.rowcount > 0
