from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from stock_simulator.db import connect
from stock_simulator.market_bar_repository import MarketBarRepository
from stock_simulator.market_bars import MarketBar
from stock_simulator.providers.yfinance import (
    confirm_with_successors,
    to_market_bars,
)
from stock_simulator.symbol_mapping import (
    SymbolMapper,
    UnknownSymbolMappingError,
)


JST = timezone(timedelta(hours=9))


def make_bar(**overrides) -> MarketBar:
    values = {
        "symbol": "7203",
        "source_symbol": "7203.T",
        "source": "yfinance",
        "timeframe": "1m",
        "bar_start_utc": datetime(2026, 11, 27, 9, 0, tzinfo=JST),
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 103.0,
        "volume": 1200.0,
        "price_basis": "raw",
        "fetched_at_utc": datetime(2026, 11, 27, 9, 2, tzinfo=JST),
        "adjusted_close": 102.0,
        "is_complete": False,
    }
    values.update(overrides)
    return MarketBar(**values)


def test_saves_ohlcv_and_preserves_existing_table_columns(tmp_path):
    conn = connect(tmp_path / "market.sqlite3")
    try:
        MarketBarRepository(conn).upsert_many([make_bar()])
        row = conn.execute("SELECT * FROM market_bars").fetchone()

        assert row["symbol"] == "7203"
        assert row["source_symbol"] == "7203.T"
        assert row["timeframe"] == "1m"
        assert row["bar_start_utc"] == "2026-11-27T00:00:00+00:00"
        assert (row["open"], row["high"], row["low"], row["close"]) == (
            100.0,
            105.0,
            99.0,
            103.0,
        )
        assert row["volume"] == 1200.0
        assert row["adjusted_close"] == 102.0
        assert row["price_basis"] == "raw"
        assert row["is_complete"] == 0
        assert [
            column["name"]
            for column in conn.execute("PRAGMA table_info(observations)")
        ] == [
            "id",
            "timestamp",
            "symbol",
            "price",
            "volume",
            "bid_price",
            "ask_price",
            "source",
        ]
        assert [
            column["name"] for column in conn.execute("PRAGMA table_info(candles)")
        ] == [
            "id",
            "symbol",
            "interval_minutes",
            "bucket_start",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "observation_count",
            "source",
        ]
    finally:
        conn.close()


def test_adds_source_symbol_to_legacy_database_and_preserves_existing_data(
    tmp_path,
):
    db_path = tmp_path / "legacy.sqlite3"
    legacy = sqlite3.connect(db_path)
    legacy.executescript(
        """
        CREATE TABLE observations (
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
        CREATE TABLE candles (
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
        CREATE TABLE market_bars (
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            bar_start_utc TEXT NOT NULL,
            source TEXT NOT NULL,
            price_basis TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL,
            adjusted_close REAL,
            fetched_at_utc TEXT NOT NULL,
            is_complete INTEGER NOT NULL,
            UNIQUE(symbol, timeframe, bar_start_utc, source, price_basis)
        );
        INSERT INTO observations (timestamp, symbol, price)
        VALUES ('2026-11-27 09:00:00', '7610', 100);
        INSERT INTO market_bars
        (symbol, timeframe, bar_start_utc, source, price_basis,
         open, high, low, close, volume, adjusted_close, fetched_at_utc, is_complete)
        VALUES
        ('7203.T', '1m', '2026-11-27T00:00:00+00:00', 'yfinance', 'raw',
         100, 105, 99, 103, 1200, 102, '2026-11-27T00:02:00+00:00', 1),
        ('9999.T', '1m', '2026-11-27T00:01:00+00:00', 'yfinance', 'raw',
         100, 105, 99, 103, 1200, 102, '2026-11-27T00:02:00+00:00', 1);
        """
    )
    old_sql = legacy.execute(
        """SELECT name, sql FROM sqlite_master
        WHERE type='table' AND name IN ('observations', 'candles')
        ORDER BY name"""
    ).fetchall()
    legacy.close()

    conn = connect(db_path)
    try:
        current_sql = conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='table' AND name IN ('observations', 'candles') "
            "ORDER BY name"
        ).fetchall()
        assert [tuple(row) for row in current_sql] == old_sql
        assert conn.execute(
            "SELECT symbol, price FROM observations"
        ).fetchone()[:] == ("7610", 100.0)
        assert [
            tuple(row)
            for row in conn.execute("SELECT is_complete FROM market_bars")
        ] == [(0,), (0,)]
        assert conn.execute(
            "SELECT COUNT(*) FROM market_bars WHERE source_symbol IS NULL"
        ).fetchone()[0] == 2

        mapper = SymbolMapper({("yfinance", "7203.T"): "7203"})
        repository = MarketBarRepository(conn)
        assert repository.migrate_legacy_symbols(mapper) == 1
        mapped = conn.execute(
            "SELECT symbol, source_symbol FROM market_bars "
            "WHERE bar_start_utc='2026-11-27T00:00:00+00:00'"
        ).fetchone()
        assert tuple(mapped) == ("7203", "7203.T")
        unknown = conn.execute(
            "SELECT symbol, source_symbol FROM market_bars "
            "WHERE bar_start_utc='2026-11-27T00:01:00+00:00'"
        ).fetchone()
        assert tuple(unknown) == ("9999.T", None)
        with pytest.raises(ValueError, match="legacy market bar"):
            repository.upsert_many(
                [
                    make_bar(
                        symbol="9999.T",
                        source_symbol="9999.T",
                        bar_start_utc=datetime(
                            2026, 11, 27, 9, 1, tzinfo=JST
                        ),
                    )
                ]
            )
    finally:
        conn.close()


def test_symbol_mapper_requires_explicit_source_symbol_mapping(tmp_path):
    mapping_file = tmp_path / "symbols.csv"
    mapping_file.write_text(
        "source,source_symbol,symbol\n"
        "yfinance,7203.T,7203\n",
        encoding="utf-8",
    )
    mapper = SymbolMapper.from_csv(mapping_file)

    assert mapper.resolve("yfinance", "7203.T") == "7203"
    with pytest.raises(UnknownSymbolMappingError, match="9999.T"):
        mapper.resolve("yfinance", "9999.T")


@pytest.mark.parametrize(
    "overrides",
    [
        {"open": float("nan")},
        {"high": 102.0},
        {"low": 101.0},
        {"close": "not-a-number"},
        {"volume": -1},
        {"adjusted_close": float("inf")},
        {"source_symbol": ""},
        {"is_complete": 1},
    ],
)
def test_rejects_invalid_market_data(overrides):
    with pytest.raises(ValueError):
        make_bar(**overrides)


def test_rejects_timezone_naive_timestamps():
    with pytest.raises(ValueError, match="bar_start_utc must include a timezone"):
        make_bar(bar_start_utc=datetime(2026, 11, 27, 9, 0))

    with pytest.raises(ValueError, match="fetched_at_utc must include a timezone"):
        make_bar(fetched_at_utc=datetime(2026, 11, 27, 9, 2))


def test_upsert_updates_newer_prices_but_never_rewinds_data_or_completion(
    tmp_path,
):
    conn = connect(tmp_path / "market.sqlite3")
    try:
        repository = MarketBarRepository(conn)
        repository.upsert_many(
            [
                make_bar(
                    close=104.0,
                    volume=1300.0,
                    fetched_at_utc=datetime(2026, 11, 27, 9, 3, tzinfo=JST),
                )
            ]
        )

        repository.upsert_many(
            [
                make_bar(
                    close=90.0,
                    open=90.0,
                    high=91.0,
                    low=89.0,
                    volume=900.0,
                    fetched_at_utc=datetime(2026, 11, 27, 9, 2, tzinfo=JST),
                    is_complete=True,
                )
            ]
        )
        row = conn.execute(
            "SELECT close, volume, fetched_at_utc, is_complete FROM market_bars"
        ).fetchone()
        assert tuple(row) == (104.0, 1300.0, "2026-11-27T00:03:00+00:00", 1)

        repository.upsert_many(
            [
                make_bar(
                    close=105.0,
                    volume=1400.0,
                    fetched_at_utc=datetime(2026, 11, 27, 9, 4, tzinfo=JST),
                    is_complete=False,
                )
            ]
        )
        row = conn.execute(
            "SELECT close, volume, fetched_at_utc, is_complete FROM market_bars"
        ).fetchone()
        assert tuple(row) == (105.0, 1400.0, "2026-11-27T00:04:00+00:00", 1)
    finally:
        conn.close()


def test_timeframe_source_and_price_basis_have_separate_rows(tmp_path):
    conn = connect(tmp_path / "market.sqlite3")
    try:
        repository = MarketBarRepository(conn)
        repository.upsert_many(
            [
                make_bar(),
                make_bar(timeframe="5m"),
                make_bar(source="another-provider", source_symbol="7203"),
                make_bar(price_basis="adjusted"),
            ]
        )
        assert conn.execute("SELECT COUNT(*) FROM market_bars").fetchone()[0] == 4
    finally:
        conn.close()


def test_last_incoming_bar_stays_incomplete_even_with_later_database_bar(tmp_path):
    conn = connect(tmp_path / "market.sqlite3")
    try:
        repository = MarketBarRepository(conn)
        later_pending = make_bar(
            bar_start_utc=datetime(2026, 11, 27, 9, 2, tzinfo=JST)
        )
        repository.upsert_many([later_pending])

        pending = repository.get_incomplete(
            ["7203"], source="yfinance", timeframe="1m", price_basis="raw"
        )
    finally:
        conn.close()

    first_time = datetime(2026, 11, 27, 9, 0, tzinfo=JST)
    second_time = datetime(2026, 11, 27, 9, 1, tzinfo=JST)
    bars = [
        make_bar(bar_start_utc=first_time),
        make_bar(bar_start_utc=second_time),
    ]

    result = confirm_with_successors(bars, pending)

    assert [bar.is_complete for bar in result] == [True, False]


def test_successor_after_trading_break_confirms_elapsed_intraday_bar():
    before_break = make_bar(
        bar_start_utc=datetime(2026, 11, 27, 11, 29, tzinfo=JST)
    )
    after_break = make_bar(
        bar_start_utc=datetime(2026, 11, 27, 12, 30, tzinfo=JST)
    )

    result = confirm_with_successors([before_break, after_break], [])

    assert result[0].is_complete is True
    assert result[1].is_complete is False


def test_successor_on_next_business_day_confirms_prior_bar():
    before_close = make_bar(
        bar_start_utc=datetime(2026, 11, 27, 15, 29, tzinfo=JST)
    )
    next_session = make_bar(
        bar_start_utc=datetime(2026, 11, 30, 9, 0, tzinfo=JST)
    )

    result = confirm_with_successors([before_close, next_session], [])

    assert result[0].is_complete is True
    assert result[1].is_complete is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"source": "another-provider", "source_symbol": "7203"},
        {"price_basis": "adjusted"},
        {"timeframe": "5m"},
    ],
)
def test_different_source_basis_or_timeframe_does_not_confirm_bar(overrides):
    first = make_bar()
    later = make_bar(
        bar_start_utc=datetime(2026, 11, 27, 9, 5, tzinfo=JST),
        **overrides,
    )

    result = confirm_with_successors([first, later], [])

    assert result[0].is_complete is False
    assert result[1].is_complete is False


def test_later_fetch_confirms_pending_bar_even_when_it_is_not_refetched(tmp_path):
    conn = connect(tmp_path / "market.sqlite3")
    try:
        repository = MarketBarRepository(conn)
        previous = make_bar()
        repository.upsert_many([previous])

        pending = repository.get_incomplete(
            ["7203"], source="yfinance", timeframe="1m", price_basis="raw"
        )
        later = make_bar(
            bar_start_utc=datetime(2026, 11, 27, 9, 1, tzinfo=JST),
            fetched_at_utc=datetime(2026, 11, 27, 9, 3, tzinfo=JST),
        )
        updates = confirm_with_successors([later], pending)
        repository.upsert_many(updates)

        rows = conn.execute(
            "SELECT bar_start_utc, is_complete FROM market_bars "
            "ORDER BY bar_start_utc"
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            ("2026-11-27T00:00:00+00:00", 1),
            ("2026-11-27T00:01:00+00:00", 0),
        ]
    finally:
        conn.close()


class FakeFrame:
    def __init__(self, rows):
        self._rows = rows

    def iterrows(self):
        return iter(self._rows)


def test_yfinance_adapter_maps_source_symbol_and_preserves_close_columns():
    frame = FakeFrame(
        [
            (
                datetime(2026, 11, 27, 9, 0, tzinfo=JST),
                {
                    "Open": 100.0,
                    "High": 105.0,
                    "Low": 99.0,
                    "Close": 103.0,
                    "Adj Close": 102.0,
                    "Volume": 1200,
                },
            )
        ]
    )
    mapper = SymbolMapper({("yfinance", "7203.T"): "7203"})
    bars = to_market_bars(
        frame,
        "7203.T",
        "1m",
        datetime(2026, 11, 27, 9, 2, tzinfo=JST),
        mapper,
    )

    assert len(bars) == 1
    assert bars[0].symbol == "7203"
    assert bars[0].source_symbol == "7203.T"
    assert bars[0].close == 103.0
    assert bars[0].adjusted_close == 102.0
    assert bars[0].price_basis == "raw"
    assert bars[0].bar_start_utc == datetime(2026, 11, 27, 0, 0, tzinfo=timezone.utc)


def test_yfinance_adapter_rejects_unknown_symbols_before_saving():
    frame = FakeFrame([])
    mapper = SymbolMapper({("yfinance", "7203.T"): "7203"})

    with pytest.raises(UnknownSymbolMappingError, match="9999.T"):
        to_market_bars(
            frame,
            "9999.T",
            "1m",
            datetime(2026, 11, 27, 9, 2, tzinfo=JST),
            mapper,
        )
