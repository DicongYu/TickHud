from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class LocalStore:
    def __init__(self, db_path: Path):
        self._path = db_path
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None

    def open(self):
        with self._lock:
            self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=3000")
            self._init_schema()

    def close(self):
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    def _init_schema(self):
        cur = self._conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS baseline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                equity_usdt REAL NOT NULL,
                realized_pnl REAL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                amount REAL NOT NULL,
                note TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                equity_usdt REAL NOT NULL,
                open_pnl REAL NOT NULL,
                daily_pnl REAL NOT NULL
            );
        """)
        try:
            self._conn.execute("ALTER TABLE baseline ADD COLUMN realized_pnl REAL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        self._conn.commit()

    def get_latest_baseline(self) -> Optional[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM baseline ORDER BY date DESC LIMIT 1"
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def save_baseline(self, date: str, equity_usdt: float, realized_pnl: float = 0.0):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO baseline (date, equity_usdt, realized_pnl, created_at) VALUES (?, ?, ?, ?)",
                (date, equity_usdt, realized_pnl, now),
            )
            self._conn.commit()

    def add_transfer(self, amount: float, note: str = ""):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO transfers (ts, amount, note) VALUES (?, ?, ?)",
                (now, amount, note),
            )
            self._conn.commit()

    def get_transfer_sum_since(self, since_date: str) -> float:
        with self._lock:
            cur = self._conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transfers WHERE ts >= ?",
                (since_date,),
            )
            return cur.fetchone()[0]

    def get_transfer_sum_between(self, since_date: str, until_date: str) -> float:
        with self._lock:
            cur = self._conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transfers WHERE ts >= ? AND ts < ?",
                (since_date, until_date),
            )
            return cur.fetchone()[0]

    def get_all_baselines(self) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM baseline ORDER BY date ASC"
            )
            return [dict(r) for r in cur.fetchall()]

    def save_snapshot(self, equity: float, open_pnl: float, daily_pnl: float):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO snapshots (ts, equity_usdt, open_pnl, daily_pnl) VALUES (?, ?, ?, ?)",
                (now, equity, open_pnl, daily_pnl),
            )
            self._conn.commit()

    def clear_all_baselines(self):
        with self._lock:
            self._conn.execute("DELETE FROM baseline")
            self._conn.commit()

    def clear_all(self):
        with self._lock:
            self._conn.execute("DELETE FROM baseline")
            self._conn.execute("DELETE FROM transfers")
            self._conn.execute("DELETE FROM snapshots")
            self._conn.commit()
