import sqlite3
from pathlib import Path

from stock_simulator.db import connect
from stock_simulator.csv_import import import_csv
from stock_simulator.candles import build_candles

def test_import_deduplicates_and_builds_candles(tmp_path: Path):
    csv_file = tmp_path / "prices.csv"
    csv_file.write_text(
        "timestamp,symbol,price,volume,bid_price,ask_price,source\n"
        "2026-11-24 09:00:10,7610,114,100,113,114,test\n"
        "2026-11-24 09:01:10,7610,115,200,114,115,test\n"
        "2026-11-24 09:04:10,7610,113,150,112,113,test\n"
        "2026-11-24 09:05:10,7610,116,300,115,116,test\n"
        "2026-11-24 09:01:10,7610,115,200,114,115,test\n",
        encoding="utf-8",
    )
    conn = connect(tmp_path / "market.sqlite3")
    result = import_csv(csv_file, conn)
    assert result.read_rows == 5
    assert result.inserted_rows == 4
    assert result.duplicate_rows == 1

    assert build_candles(conn, 5, "incremental") == 2
    rows = conn.execute(
        "SELECT bucket_start, open, high, low, close, volume, observation_count "
        "FROM candles ORDER BY bucket_start"
    ).fetchall()
    assert len(rows) == 2
    assert tuple(rows[0]) == ("2026-11-24 09:00:00", 114.0, 115.0, 113.0, 113.0, 450.0, 3)
    assert tuple(rows[1]) == ("2026-11-24 09:05:00", 116.0, 116.0, 116.0, 116.0, 300.0, 1)
    conn.close()

def test_rejects_invalid_rows(tmp_path: Path):
    csv_file = tmp_path / "bad.csv"
    csv_file.write_text(
        "timestamp,symbol,price\n"
        "not-a-date,7610,100\n"
        "2026-11-24 09:00:00,7610,-1\n"
        "2026-11-24 09:01:00,7610,101\n",
        encoding="utf-8",
    )
    conn = connect(tmp_path / "db.sqlite3")
    result = import_csv(csv_file, conn)
    assert result.inserted_rows == 1
    assert result.rejected_rows == 2
    conn.close()
