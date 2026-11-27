from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import re
from numbers import Real


_MINUTE_TIMEFRAME = re.compile(r"^[1-9][0-9]*m$")


def timeframe_duration(timeframe: str) -> timedelta:
    if not isinstance(timeframe, str) or not _MINUTE_TIMEFRAME.fullmatch(timeframe):
        raise ValueError("timeframe must be a positive minute interval such as 1m")
    return timedelta(minutes=int(timeframe[:-1]))


def _utc_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value.astimezone(timezone.utc)


def _positive_number(value: Real, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field_name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field_name} must be finite and greater than zero")
    return number


def _optional_nonnegative_number(
    value: Real | None, field_name: str
) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field_name} must be numeric or None")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field_name} must be finite and not negative")
    return number


@dataclass(frozen=True)
class MarketBar:
    symbol: str
    source_symbol: str
    source: str
    timeframe: str
    bar_start_utc: datetime
    open: Real
    high: Real
    low: Real
    close: Real
    volume: Real | None
    price_basis: str
    fetched_at_utc: datetime
    adjusted_close: Real | None = None
    is_complete: bool = False

    def __post_init__(self) -> None:
        for field_name in ("symbol", "source_symbol", "source", "price_basis"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")

        timeframe_duration(self.timeframe)
        if not isinstance(self.is_complete, bool):
            raise ValueError("is_complete must be a boolean")

        bar_start = _utc_datetime(self.bar_start_utc, "bar_start_utc")
        fetched_at = _utc_datetime(self.fetched_at_utc, "fetched_at_utc")
        object.__setattr__(self, "bar_start_utc", bar_start)
        object.__setattr__(self, "fetched_at_utc", fetched_at)

        open_price = _positive_number(self.open, "open")
        high_price = _positive_number(self.high, "high")
        low_price = _positive_number(self.low, "low")
        close_price = _positive_number(self.close, "close")
        volume = _optional_nonnegative_number(self.volume, "volume")
        adjusted_close = _optional_nonnegative_number(
            self.adjusted_close, "adjusted_close"
        )
        if adjusted_close == 0:
            raise ValueError("adjusted_close must be greater than zero when provided")

        if high_price < max(open_price, close_price, low_price):
            raise ValueError("high must be greater than or equal to open, close, and low")
        if low_price > min(open_price, close_price, high_price):
            raise ValueError("low must be less than or equal to open, close, and high")

        object.__setattr__(self, "open", open_price)
        object.__setattr__(self, "high", high_price)
        object.__setattr__(self, "low", low_price)
        object.__setattr__(self, "close", close_price)
        object.__setattr__(self, "volume", volume)
        object.__setattr__(self, "adjusted_close", adjusted_close)
