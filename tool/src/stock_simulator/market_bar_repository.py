from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Iterable, Sequence

from .market_bars import MarketBar
from .symbol_mapping import SymbolMapper


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class MarketBarRepository:
    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection

    def upsert_many(self, bars: Iterable[MarketBar]) -> int:
        records = []
        for bar in bars:
            if not isinstance(bar, MarketBar):
                raise TypeError("bars must contain only MarketBar instances")
            legacy = self._connection.execute(
                """SELECT source_symbol FROM market_bars
                   WHERE symbol=? AND timeframe=? AND bar_start_utc=?
                     AND source=? AND price_basis=?""",
                (
                    bar.symbol,
                    bar.timeframe,
                    _timestamp(bar.bar_start_utc),
                    bar.source,
                    bar.price_basis,
                ),
            ).fetchone()
            if legacy is not None and legacy["source_symbol"] is None:
                raise ValueError(
                    "Cannot update a legacy market bar without source_symbol; "
                    "add an explicit symbol mapping first"
                )
            records.append(
                (
                    bar.symbol,
                    bar.source_symbol,
                    bar.timeframe,
                    _timestamp(bar.bar_start_utc),
                    bar.source,
                    bar.price_basis,
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    bar.volume,
                    bar.adjusted_close,
                    _timestamp(bar.fetched_at_utc),
                    int(bar.is_complete),
                )
            )

        if not records:
            return 0

        with self._connection:
            self._connection.executemany(
                """INSERT INTO market_bars
                (symbol, source_symbol, timeframe, bar_start_utc, source, price_basis,
                 open, high, low, close, volume, adjusted_close,
                 fetched_at_utc, is_complete)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timeframe, bar_start_utc, source, price_basis)
                DO UPDATE SET
                    source_symbol=CASE
                        WHEN excluded.fetched_at_utc > market_bars.fetched_at_utc
                        THEN excluded.source_symbol ELSE market_bars.source_symbol END,
                    open=CASE
                        WHEN excluded.fetched_at_utc > market_bars.fetched_at_utc
                        THEN excluded.open ELSE market_bars.open END,
                    high=CASE
                        WHEN excluded.fetched_at_utc > market_bars.fetched_at_utc
                        THEN excluded.high ELSE market_bars.high END,
                    low=CASE
                        WHEN excluded.fetched_at_utc > market_bars.fetched_at_utc
                        THEN excluded.low ELSE market_bars.low END,
                    close=CASE
                        WHEN excluded.fetched_at_utc > market_bars.fetched_at_utc
                        THEN excluded.close ELSE market_bars.close END,
                    volume=CASE
                        WHEN excluded.fetched_at_utc > market_bars.fetched_at_utc
                        THEN excluded.volume ELSE market_bars.volume END,
                    adjusted_close=CASE
                        WHEN excluded.fetched_at_utc > market_bars.fetched_at_utc
                        THEN excluded.adjusted_close ELSE market_bars.adjusted_close END,
                    fetched_at_utc=CASE
                        WHEN excluded.fetched_at_utc > market_bars.fetched_at_utc
                        THEN excluded.fetched_at_utc ELSE market_bars.fetched_at_utc END,
                    is_complete=MAX(market_bars.is_complete, excluded.is_complete)""",
                records,
            )
        return len(records)

    def get_incomplete(
        self,
        symbols: Sequence[str],
        source: str,
        timeframe: str,
        price_basis: str,
    ) -> list[MarketBar]:
        unique_symbols = sorted(set(symbols))
        if not unique_symbols:
            return []

        placeholders = ", ".join("?" for _ in unique_symbols)
        rows = self._connection.execute(
            f"""SELECT symbol, source_symbol, source, timeframe, bar_start_utc,
                       open, high, low, close, volume, adjusted_close,
                       price_basis, fetched_at_utc, is_complete
                FROM market_bars
                WHERE is_complete=0 AND source_symbol IS NOT NULL
                  AND source=? AND timeframe=? AND price_basis=?
                  AND symbol IN ({placeholders})""",
            (source, timeframe, price_basis, *unique_symbols),
        ).fetchall()
        return [self._to_market_bar(row) for row in rows]

    def migrate_legacy_symbols(self, mapper: SymbolMapper) -> int:
        rows = self._connection.execute(
            """SELECT rowid, symbol, source, timeframe, bar_start_utc, price_basis,
                      source_symbol
               FROM market_bars"""
        ).fetchall()

        updates = []
        for row in rows:
            if row["source_symbol"] is not None:
                continue
            internal_symbol = mapper.lookup(row["source"], row["symbol"])
            if internal_symbol is None:
                continue

            conflict = self._connection.execute(
                """SELECT rowid FROM market_bars
                   WHERE symbol=? AND timeframe=? AND bar_start_utc=?
                     AND source=? AND price_basis=? AND rowid<>?""",
                (
                    internal_symbol,
                    row["timeframe"],
                    row["bar_start_utc"],
                    row["source"],
                    row["price_basis"],
                    row["rowid"],
                ),
            ).fetchone()
            if conflict is not None:
                raise ValueError(
                    "Symbol mapping would merge existing market_bars records: "
                    f"{row['source']} / {row['symbol']} -> {internal_symbol}"
                )
            updates.append((internal_symbol, row["symbol"], row["rowid"]))

        with self._connection:
            for internal_symbol, source_symbol, rowid in updates:
                self._connection.execute(
                    """UPDATE market_bars
                       SET symbol=?, source_symbol=?
                       WHERE rowid=?""",
                    (internal_symbol, source_symbol, rowid),
                )
        return len(updates)

    @staticmethod
    def _to_market_bar(row: sqlite3.Row) -> MarketBar:
        return MarketBar(
            symbol=row["symbol"],
            source_symbol=row["source_symbol"],
            source=row["source"],
            timeframe=row["timeframe"],
            bar_start_utc=datetime.fromisoformat(row["bar_start_utc"]),
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
            adjusted_close=row["adjusted_close"],
            price_basis=row["price_basis"],
            fetched_at_utc=datetime.fromisoformat(row["fetched_at_utc"]),
            is_complete=bool(row["is_complete"]),
        )
