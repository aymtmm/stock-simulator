from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

def _bucket(dt: datetime, minutes: int) -> datetime:
    minute = (dt.minute // minutes) * minutes
    return dt.replace(minute=minute, second=0, microsecond=0)

def build_candles(conn, interval_minutes: int, volume_mode: str = "incremental") -> int:
    """
    Build OHLC candles from timestamped price observations.

    volume_mode:
      incremental: each row's volume is volume traded since previous observation;
                   values inside each bucket are summed.
      cumulative:  each row's volume is a running cumulative counter; deltas between
                   consecutive observations are attributed to the later observation's bucket.
      none:        volume is stored as NULL.

    The first cumulative observation for each symbol has no measurable delta and is excluded.
    """
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be greater than zero")
    if volume_mode not in {"incremental", "cumulative", "none"}:
        raise ValueError("volume_mode must be incremental, cumulative, or none")

    rows = conn.execute(
        """SELECT timestamp, symbol, price, volume
           FROM observations
           ORDER BY symbol, timestamp, id"""
    ).fetchall()

    grouped = defaultdict(list)
    previous_cumulative = {}

    for row in rows:
        dt = datetime.fromisoformat(row["timestamp"])
        symbol = row["symbol"]
        volume = None

        if volume_mode == "incremental":
            volume = row["volume"]
        elif volume_mode == "cumulative":
            current = row["volume"]
            previous = previous_cumulative.get(symbol)
            if current is not None and previous is not None and current >= previous:
                volume = current - previous
            elif current is not None and previous is not None and current < previous:
                # Counter reset (commonly a new trading day): treat current as the new baseline.
                volume = 0.0
            previous_cumulative[symbol] = current
        # volume_mode == none leaves volume as None

        bucket = _bucket(dt, interval_minutes)
        grouped[(symbol, bucket)].append((dt, float(row["price"]), volume))

    count = 0
    for (symbol, bucket), items in grouped.items():
        items.sort(key=lambda x: x[0])
        prices = [x[1] for x in items]
        vols = [x[2] for x in items if x[2] is not None]
        total_volume = sum(vols) if vols else None
        conn.execute(
            """INSERT INTO candles
            (symbol, interval_minutes, bucket_start, open, high, low, close,
             volume, observation_count, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'derived')
            ON CONFLICT(symbol, interval_minutes, bucket_start, source)
            DO UPDATE SET open=excluded.open, high=excluded.high, low=excluded.low,
              close=excluded.close, volume=excluded.volume,
              observation_count=excluded.observation_count""",
            (symbol, interval_minutes, bucket.isoformat(sep=" "),
             prices[0], max(prices), min(prices), prices[-1],
             total_volume, len(items)),
        )
        count += 1

    conn.commit()
    return count
