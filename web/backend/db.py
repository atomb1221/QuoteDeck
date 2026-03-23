"""SQLite database for PocketPricer — customers, quotes, users, sessions, products."""
import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import bcrypt


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
        self._migrate()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    username      TEXT    UNIQUE NOT NULL,
                    password_hash TEXT    NOT NULL,
                    created_at    TEXT    DEFAULT (datetime('now')),
                    last_login    TEXT
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token      TEXT    PRIMARY KEY,
                    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TEXT    DEFAULT (datetime('now')),
                    expires_at TEXT    NOT NULL
                );
                CREATE TABLE IF NOT EXISTS customers (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    name       TEXT    NOT NULL,
                    created_at TEXT    DEFAULT (datetime('now')),
                    UNIQUE(user_id, name)
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
                    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
                    name        TEXT    NOT NULL,
                    total_value REAL    NOT NULL,
                    items_count INTEGER NOT NULL,
                    quote_data  TEXT    NOT NULL,
                    created_at  TEXT    DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS products (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    code        TEXT    NOT NULL DEFAULT '',
                    description TEXT    NOT NULL DEFAULT '',
                    weight      REAL    NOT NULL DEFAULT 0.0,
                    type        TEXT    NOT NULL DEFAULT '',
                    created_at  TEXT    DEFAULT (datetime('now'))
                );
            """)
            conn.commit()

    def _migrate(self):
        """Upgrade schema for databases created before the current version."""
        with self._conn() as conn:
            # ── customers: add user_id, change UNIQUE from (name) to (user_id, name) ──
            cols = {r[1] for r in conn.execute("PRAGMA table_info(customers)").fetchall()}
            if "user_id" not in cols:
                conn.executescript("""
                    PRAGMA foreign_keys = OFF;
                    ALTER TABLE customers RENAME TO _customers_old;
                    CREATE TABLE customers (
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
                        name       TEXT    NOT NULL,
                        created_at TEXT    DEFAULT (datetime('now')),
                        UNIQUE(user_id, name)
                    );
                    INSERT OR IGNORE INTO customers (id, user_id, name, created_at)
                        SELECT id, 1, name, created_at FROM _customers_old;
                    DROP TABLE _customers_old;
                    PRAGMA foreign_keys = ON;
                """)
                conn.commit()

            # ── quotes: add user_id ────────────────────────────────────────────
            q_cols = {r[1] for r in conn.execute("PRAGMA table_info(quotes)").fetchall()}
            if "user_id" not in q_cols:
                conn.execute("ALTER TABLE quotes ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
                conn.execute("UPDATE quotes SET user_id = 1 WHERE user_id IS NULL")
                conn.commit()

            # ── customer_prices: add steel_description (legacy) ────────────────
            try:
                conn.execute("ALTER TABLE customer_prices ADD COLUMN steel_description TEXT DEFAULT ''")
                conn.commit()
            except Exception:
                pass

    # ── Products ───────────────────────────────────────────────────────────────

    def get_products(self, user_id: int) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, code, description, weight, type FROM products WHERE user_id = ? ORDER BY id",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def has_products(self, user_id: int) -> bool:
        with self._conn() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM products WHERE user_id = ?", (user_id,)
            ).fetchone()[0]
        return count > 0

    def seed_products(self, user_id: int, products: List[Dict]):
        """Bulk-insert a product list for a user (used on first run)."""
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO products (user_id, code, description, weight, type) VALUES (?, ?, ?, ?, ?)",
                [(user_id, p["code"], p["description"], p["weight"], p.get("type", ""))
                 for p in products],
            )
            conn.commit()

    def add_product(self, user_id: int, code: str, description: str, weight: float, type_: str) -> Dict:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO products (user_id, code, description, weight, type) VALUES (?, ?, ?, ?, ?)",
                (user_id, code, description, weight, type_),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id, code, description, weight, type FROM products WHERE id = ?",
                (cur.lastrowid,),
            ).fetchone()
        return dict(row)

    def update_product(self, product_id: int, user_id: int, code: str, description: str,
                       weight: float, type_: str) -> Optional[Dict]:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE products SET code=?, description=?, weight=?, type=? WHERE id=? AND user_id=?",
                (code, description, weight, type_, product_id, user_id),
            )
            conn.commit()
            if cur.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT id, code, description, weight, type FROM products WHERE id = ?",
                (product_id,),
            ).fetchone()
        return dict(row)

    def delete_product(self, product_id: int, user_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM products WHERE id = ? AND user_id = ?",
                (product_id, user_id),
            )
            conn.commit()
        return cur.rowcount > 0

    # ── Customers ──────────────────────────────────────────────────────────────

    def search_customers(self, query: str, user_id: int, limit: int = 8) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, name FROM customers WHERE user_id = ? AND name LIKE ? ORDER BY name LIMIT ?",
                (user_id, f"%{query}%", limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def find_or_create_customer(self, name: str, user_id: int) -> Dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, name FROM customers WHERE user_id = ? AND name = ?",
                (user_id, name),
            ).fetchone()
            if row:
                return dict(row)
            conn.execute(
                "INSERT INTO customers (user_id, name) VALUES (?, ?)", (user_id, name)
            )
            conn.commit()
            row = conn.execute(
                "SELECT id, name FROM customers WHERE user_id = ? AND name = ?",
                (user_id, name),
            ).fetchone()
        return dict(row)

    def get_customer_quotes(self, customer_id: int, limit: int = 3) -> List[Dict]:
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

    def list_quotes(self, user_id: int, limit: int = 100) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT q.id, q.name, q.total_value, q.items_count, q.created_at,
                          c.name AS customer_name
                   FROM quotes q
                   LEFT JOIN customers c ON q.customer_id = c.id
                   WHERE q.user_id = ?
                   ORDER BY q.created_at DESC LIMIT ?""",
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def save_quote(self, customer_id: Optional[int], name: str, total_value: float,
                   items_count: int, quote_data: list, user_id: Optional[int] = None) -> Dict:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO quotes (user_id, customer_id, name, total_value, items_count, quote_data)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, customer_id, name, total_value, items_count, json.dumps(quote_data)),
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

    # ── Users ──────────────────────────────────────────────────────────────────

    def get_all_users(self) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT id, username FROM users").fetchall()
        return [dict(r) for r in rows]

    def verify_user(self, username: str, password: str) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, username, password_hash FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        if not row:
            return None
        user = dict(row)
        if bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
            return {"id": user["id"], "username": user["username"]}
        return None

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        expires = (datetime.now() + timedelta(days=30)).isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user_id, expires),
            )
            conn.execute(
                "UPDATE users SET last_login = datetime('now') WHERE id = ?", (user_id,)
            )
            conn.commit()
        return token

    def get_session_user(self, token: str) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT u.id, u.username
                   FROM sessions s JOIN users u ON s.user_id = u.id
                   WHERE s.token = ? AND s.expires_at > datetime('now')""",
                (token,),
            ).fetchone()
        return dict(row) if row else None

    def delete_session(self, token: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()

    def seed_admin_if_empty(self, products: List[Dict] = None):
        """Create admin/admin if no users exist. Seeds products if provided."""
        with self._conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if count == 0:
                pw_hash = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode()
                cur = conn.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    ("admin", pw_hash),
                )
                user_id = cur.lastrowid
                conn.commit()
                if products:
                    self.seed_products(user_id, products)
                return

        # Users already exist — ensure every user has a product list
        if products:
            for user in self.get_all_users():
                if not self.has_products(user["id"]):
                    self.seed_products(user["id"], products)
