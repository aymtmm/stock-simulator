from __future__ import annotations

import argparse
from pathlib import Path

from .db import connect
from .csv_import import import_csv
from .candles import build_candles

DEFAULT_DB = Path("data/database/market.sqlite3")

def main():
    parser = argparse.ArgumentParser(prog="stock-sim", description="Stock market data foundation")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Import normalized CSV into SQLite")
    p_ingest.add_argument("csv_file")
    p_ingest.add_argument("--db", default=str(DEFAULT_DB))
    p_ingest.add_argument("--source", default="csv")

    p_candles = sub.add_parser("candles", help="Build OHLC candles")
    p_candles.add_argument("--db", default=str(DEFAULT_DB))
    p_candles.add_argument("--interval", type=int, default=5)
    p_candles.add_argument("--volume-mode", choices=["incremental", "cumulative", "none"],
                            default="incremental")

    p_status = sub.add_parser("status", help="Show database row counts")
    p_status.add_argument("--db", default=str(DEFAULT_DB))

    args = parser.parse_args()
    conn = connect(args.db)
    try:
        if args.command == "ingest":
            result = import_csv(args.csv_file, conn, args.source)
            print(f"Read: {result.read_rows}")
            print(f"Inserted: {result.inserted_rows}")
            print(f"Duplicates: {result.duplicate_rows}")
            print(f"Rejected: {result.rejected_rows}")
            for error in result.errors[:20]:
                print(f"ERROR: {error}")
            if len(result.errors) > 20:
                print(f"... and {len(result.errors) - 20} more errors")
        elif args.command == "candles":
            count = build_candles(conn, args.interval, args.volume_mode)
            print(f"Generated/updated candles: {count}")
        elif args.command == "status":
            obs = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            candles = conn.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
            print(f"Observations: {obs}")
            print(f"Candles: {candles}")
            print(f"Database: {Path(args.db).resolve()}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
