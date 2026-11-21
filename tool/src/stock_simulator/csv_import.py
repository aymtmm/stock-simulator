from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

REQUIRED = {"timestamp", "symbol", "price"}
OPTIONAL = {"volume", "bid_price", "ask_price", "source"}

@dataclass
class ImportResult:
    read_rows: int = 0
    inserted_rows: int = 0
    duplicate_rows: int = 0
    rejected_rows: int = 0
    errors: list[str] | None = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

def _number(value: str | None, field: str, line: int) -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        result = float(value)
    except ValueError as exc:
        raise ValueError(f"line {line}: {field} must be numeric") from exc
    if result < 0:
        raise ValueError(f"line {line}: {field} must not be negative")
    return result

def _timestamp(value: str, line: int) -> str:
    try:
        dt = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(
            f"line {line}: invalid timestamp '{value}'. "
            "Use YYYY-MM-DD HH:MM:SS or ISO 8601."
        ) from exc
    if dt.tzinfo is not None:
        # Store a normalized, timezone-aware ISO string; callers should use one timezone consistently.
        return dt.isoformat(timespec="seconds")
    return dt.isoformat(sep=" ", timespec="seconds")

def import_csv(csv_path: str | Path, conn, default_source: str = "csv") -> ImportResult:
    result = ImportResult()
    path = Path(csv_path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        missing = REQUIRED - headers
        if missing:
            raise ValueError(f"Missing required CSV columns: {', '.join(sorted(missing))}")

        for line, row in enumerate(reader, start=2):
            result.read_rows += 1
            try:
                timestamp = _timestamp(row.get("timestamp", ""), line)
                symbol = (row.get("symbol") or "").strip()
                if not symbol:
                    raise ValueError(f"line {line}: symbol is empty")
                price = _number(row.get("price"), "price", line)
                if price is None or price <= 0:
                    raise ValueError(f"line {line}: price must be greater than zero")
                volume = _number(row.get("volume"), "volume", line)
                bid = _number(row.get("bid_price"), "bid_price", line)
                ask = _number(row.get("ask_price"), "ask_price", line)
                if bid is not None and bid <= 0:
                    raise ValueError(f"line {line}: bid_price must be greater than zero")
                if ask is not None and ask <= 0:
                    raise ValueError(f"line {line}: ask_price must be greater than zero")
                source = (row.get("source") or default_source).strip() or default_source

                cur = conn.execute(
                    """INSERT OR IGNORE INTO observations
                    (timestamp, symbol, price, volume, bid_price, ask_price, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (timestamp, symbol, price, volume, bid, ask, source),
                )
                if cur.rowcount == 1:
                    result.inserted_rows += 1
                else:
                    result.duplicate_rows += 1
            except ValueError as exc:
                result.rejected_rows += 1
                result.errors.append(str(exc))

    conn.commit()
    return result
