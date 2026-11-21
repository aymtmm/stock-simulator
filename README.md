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

## Database

Default path: `data/database/market.sqlite3`

Tables:

- `observations`: normalized source observations, unique by timestamp + symbol + source
- `candles`: derived OHLCV data, unique by symbol + interval + bucket + source

Raw observations are retained. Candles can be rebuilt at any interval.

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
