from pathlib import Path
import sqlite3

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    price REAL NOT NULL CHECK(price > 0),
    volume REAL,
    bid_price REAL,
    ask_price REAL,
    source TEXT NOT NULL DEFAULT 'csv',
    UNIQUE(timestamp, symbol, source)
);

CREATE INDEX IF NOT EXISTS idx_observations_symbol_time
ON observations(symbol, timestamp);

CREATE TABLE IF NOT EXISTS candles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    interval_minutes INTEGER NOT NULL CHECK(interval_minutes > 0),
    bucket_start TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL,
    observation_count INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'derived',
    UNIQUE(symbol, interval_minutes, bucket_start, source)
);

CREATE INDEX IF NOT EXISTS idx_candles_symbol_interval_time
ON candles(symbol, interval_minutes, bucket_start);
"""

def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
