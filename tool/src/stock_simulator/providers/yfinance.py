from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import math
from typing import Iterable, Literal, overload, Protocol, Sequence

from ..market_bars import MarketBar, timeframe_duration
from ..symbol_mapping import SymbolMapper


class _YFinanceRow(Protocol):
    def get(self, key: str, default: object = None) -> object: ...


class _YFinanceFrame(Protocol):
    def iterrows(self) -> Iterable[tuple[datetime, _YFinanceRow]]: ...


@overload
def _number(value: object, field_name: str) -> float: ...


@overload
def _number(
    value: object, field_name: str, *, optional: Literal[True]
) -> float | None: ...


def _number(
    value: object, field_name: str, *, optional: bool = False
) -> float | None:
    if value is None:
        if optional:
            return None
        raise ValueError(f"{field_name} is required")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if math.isnan(number) and optional:
        return None
    return number


def to_market_bars(
    frame: _YFinanceFrame,
    source_symbol: str,
    timeframe: str,
    fetched_at_utc: datetime,
    mapper: SymbolMapper,
) -> list[MarketBar]:
    """Convert a single-symbol yfinance history frame to provider-neutral bars."""
    timeframe_duration(timeframe)
    symbol = mapper.resolve("yfinance", source_symbol)
    bars = []
    for timestamp, row in frame.iterrows():
        if not isinstance(timestamp, datetime):
            raise ValueError(f"{source_symbol}: bar timestamp must be a datetime")
        bars.append(
            MarketBar(
                symbol=symbol,
                source_symbol=source_symbol,
                source="yfinance",
                timeframe=timeframe,
                bar_start_utc=timestamp,
                open=_number(row.get("Open"), "Open"),
                high=_number(row.get("High"), "High"),
                low=_number(row.get("Low"), "Low"),
                close=_number(row.get("Close"), "Close"),
                volume=_number(row.get("Volume"), "Volume", optional=True),
                adjusted_close=_number(
                    row.get("Adj Close"), "Adj Close", optional=True
                ),
                price_basis="raw",
                fetched_at_utc=fetched_at_utc,
            )
        )
    bars.sort(key=lambda bar: bar.bar_start_utc)
    if any(
        previous.bar_start_utc == current.bar_start_utc
        for previous, current in zip(bars, bars[1:])
    ):
        raise ValueError(f"{source_symbol}: duplicate yfinance bar timestamps")
    return bars


def confirm_with_successors(
    bars: Sequence[MarketBar],
    pending_bars: Sequence[MarketBar],
) -> list[MarketBar]:
    """Confirm bars only when a later bar proves their nominal interval has ended."""
    incoming_by_key = {_bar_key(bar): bar for bar in bars}
    pending_by_key = {
        _bar_key(bar): bar
        for bar in pending_bars
        if _bar_key(bar) not in incoming_by_key
    }

    def group_key(bar: MarketBar) -> tuple[str, str, str, str]:
        return (bar.symbol, bar.source, bar.timeframe, bar.price_basis)

    incoming_groups: dict[tuple[str, str, str, str], list[MarketBar]] = {}
    pending_groups: dict[tuple[str, str, str, str], list[MarketBar]] = {}
    for bar in incoming_by_key.values():
        incoming_groups.setdefault(group_key(bar), []).append(bar)
    for bar in pending_by_key.values():
        pending_groups.setdefault(group_key(bar), []).append(bar)

    confirmed = dict(incoming_by_key)
    for key, incoming_group in incoming_groups.items():
        incoming_group.sort(key=lambda bar: bar.bar_start_utc)
        for index, bar in enumerate(incoming_group[:-1]):
            if bar.is_complete:
                continue
            interval_end = bar.bar_start_utc + timeframe_duration(bar.timeframe)
            has_successor = any(
                later.bar_start_utc >= interval_end
                for later in incoming_group[index + 1 :]
            )
            if has_successor:
                confirmed[_bar_key(bar)] = replace(bar, is_complete=True)

        for bar in pending_groups.get(key, []):
            if bar.is_complete:
                continue
            interval_end = bar.bar_start_utc + timeframe_duration(bar.timeframe)
            has_successor = any(
                incoming.bar_start_utc >= interval_end
                for incoming in incoming_group
            )
            if has_successor:
                confirmed[_bar_key(bar)] = replace(bar, is_complete=True)

    result = [confirmed[key] for key in incoming_by_key]
    for key, bar in pending_by_key.items():
        updated = confirmed.get(key, bar)
        if not bar.is_complete and updated.is_complete:
            result.append(updated)
    return result


def _bar_key(bar: MarketBar) -> tuple[str, str, str, datetime, str]:
    return (
        bar.symbol,
        bar.source,
        bar.timeframe,
        bar.bar_start_utc,
        bar.price_basis,
    )
