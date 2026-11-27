# Stock Simulator - Phase 1

CSV-first Japanese stock market data foundation. This phase does **not** place real orders.

## Requirements

- Windows 10/11
- Python 3.10 or newer (Python 3.12 recommended)
- VS Code optional

The core application uses only Python's standard library. `pytest` is used for tests.

## CSV format

Required columns:

- `timestamp`: `YYYY-MM-DD HH:MM:SS` or ISO 8601
- `symbol`: stock code, e.g. `7610`
- `price`: observed price, greater than zero

Optional columns:

- `volume`: volume value (meaning depends on `--volume-mode`)
- `bid_price`: bid quote
- `ask_price`: ask quote
- `source`: data source label

Example: `sample_ticks.csv`.

### Important: volume semantics

Do not mix volume definitions.

- `incremental`: each row's volume is the amount traded since the previous observation. Candle builder sums values inside each interval.
- `cumulative`: each row's volume is the running cumulative counter. Candle builder calculates differences between consecutive observations. The first observation has no measurable delta.
- `none`: ignore volume.

If the source's volume meaning is unknown, use `none` until verified. A snapshot of cumulative daily volume must **not** be summed directly.

All timestamps should use one consistent timezone. For Japanese market data, use Japan Standard Time consistently.

## Windows setup (PowerShell)

Open PowerShell in this project directory:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

If PowerShell blocks activation, run this for the current terminal only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Commands

Import sample data:

```powershell
stock-sim ingest .\sample_ticks.csv
```

Build 5-minute candles from incremental volume:

```powershell
stock-sim candles --interval 5 --volume-mode incremental
```

Build 1-, 3-, 15-, or 60-minute candles:

```powershell
stock-sim candles --interval 1 --volume-mode incremental
stock-sim candles --interval 3 --volume-mode incremental
stock-sim candles --interval 15 --volume-mode incremental
stock-sim candles --interval 60 --volume-mode incremental
```

Show database status:

```powershell
stock-sim status
```

You can also run without installing the command:

```powershell
python -m stock_simulator.cli ingest .\sample_ticks.csv
```

Import yfinance OHLCV bars into SQLite (from this directory, after installing the
core package and the yfinance test requirements):

```powershell
pip install -e .
pip install -r ..\yfinance_jp_test\requirements.txt
python ..\yfinance_jp_test\fetch_yfinance.py --interval 1m --save-to-db
```

Use `--tickers` to select symbols, `--interval 5m` for five-minute bars, and
`--db .\data\database\market.sqlite3` to select the database. CSV output is
still written as before. Database persistence is opt-in via `--save-to-db`.

## Database

Default path: `data/database/market.sqlite3`

Tables:

- `observations`: normalized source observations, unique by timestamp + symbol + source
- `candles`: derived OHLCV data, unique by symbol + interval + bucket + source
- `market_bars`: provider OHLCV bars, including internal `symbol` and original `source_symbol`; unique by symbol + timeframe + UTC bar start + source + price basis

Raw observations are retained. Candles can be rebuilt at any interval.
`market_bars` keeps the source OHLCV separate from candles derived from observations.
Its `adjusted_close` is stored separately; `open`, `high`, `low`, and `close` remain
the unadjusted values returned with `auto_adjust=False`. New imports require an
explicit mapping in `..\yfinance_jp_test\symbol_mappings.csv`; an unmapped source
symbol aborts the database batch rather than being guessed. Only minute intervals
are accepted. Bar timestamps must include a timezone and are stored in UTC.

`is_complete` is based on observing a later bar for the same symbol, source,
timeframe, and price basis whose start is at or after the current bar's nominal end.
The last bar in a response is therefore incomplete, regardless of wall-clock time.
Previously stored incomplete bars can be confirmed when a later bar is observed.
This confirms that the nominal interval has passed; yfinance does not provide an
authoritative finality signal, and it does not guarantee that the provider will
never revise historical values. Newer fetches may correct OHLCV values, while
completion never regresses. Older fetches cannot overwrite newer prices. Missing
bars are not deleted.

Opening a database created by the earlier Phase 1 integration adds
`market_bars.source_symbol` and resets its prior time-based completion flags to
incomplete. The next yfinance database import applies explicit mappings to known
legacy symbols; unknown legacy rows are preserved with a NULL `source_symbol`.
`observations` and `candles` are not migrated or modified.

## Tests

```powershell
pytest
```

## Known limitations in Phase 1

- This is a data foundation, not a trading strategy or brokerage integration.
- CSV rows are observations; they are not necessarily every individual trade.
- OHLC values are only as accurate as the input sampling frequency.
- Bid/ask values are stored for future spread-aware simulation but are not yet used for execution simulation.
- The current candle builder treats each calendar interval independently. Exchange-session rules, lunch breaks, holidays, and daylight/timezone validation will be added before strategy backtesting.
- Duplicate key is `(timestamp, symbol, source)`. If a provider emits multiple distinct observations with the same timestamp, the ingestion key will need a provider-specific sequence or event ID.
