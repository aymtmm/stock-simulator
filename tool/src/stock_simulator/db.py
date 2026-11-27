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

CREATE TABLE IF NOT EXISTS market_bars (
    symbol TEXT NOT NULL,
    source_symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    bar_start_utc TEXT NOT NULL,
    source TEXT NOT NULL,
    price_basis TEXT NOT NULL,
    open REAL NOT NULL CHECK(open > 0),
    high REAL NOT NULL CHECK(high > 0),
    low REAL NOT NULL CHECK(low > 0),
    close REAL NOT NULL CHECK(close > 0),
    volume REAL CHECK(volume IS NULL OR volume >= 0),
    adjusted_close REAL CHECK(adjusted_close IS NULL OR adjusted_close > 0),
    fetched_at_utc TEXT NOT NULL,
    is_complete INTEGER NOT NULL CHECK(is_complete IN (0, 1)),
    UNIQUE(symbol, timeframe, bar_start_utc, source, price_basis)
);

CREATE INDEX IF NOT EXISTS idx_market_bars_symbol_time
ON market_bars(symbol, bar_start_utc);
"""

def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate_market_bars(conn)
    return conn


def _migrate_market_bars(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(market_bars)")
    }
    if "source_symbol" not in columns:
        with conn:
            conn.execute("ALTER TABLE market_bars ADD COLUMN source_symbol TEXT")
            conn.execute("UPDATE market_bars SET is_complete = 0")
