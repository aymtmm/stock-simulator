from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf


JST = ZoneInfo("Asia/Tokyo")
DEFAULT_TICKERS = ["7203.T", "6758.T", "9984.T"]


def fetch_one(ticker: str, period: str, interval: str) -> pd.DataFrame:
    stock = yf.Ticker(ticker)
    data = stock.history(
        period=period,
        interval=interval,
        auto_adjust=False,
        actions=False,
        prepost=False,
        timeout=20,
    )
    if data.empty:
        print(f"[WARN] {ticker}: データが取得できませんでした")
        return data

    data = data.copy()
    # yfinanceのindexは通常タイムゾーン付き。CSVにも日時を残す。
    data.index.name = "timestamp"
    data.insert(0, "symbol", ticker)
    return data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="yfinanceで日本株の分足データを取得してCSV保存します"
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=DEFAULT_TICKERS,
        help="Yahoo Financeの銘柄コード (例: 7203.T 6758.T)",
    )
    parser.add_argument("--period", default="1d", help="取得期間 (例: 1d, 5d)")
    parser.add_argument("--interval", default="1m", help="足種 (例: 1m, 2m, 5m)")
    parser.add_argument("--output-dir", default="output", help="CSV出力先")
    args = parser.parse_args()

    now = datetime.now(JST)
    print("=" * 72)
    print("yfinance 日本株データ取得テスト")
    print(f"取得実行時刻(JST): {now:%Y-%m-%d %H:%M:%S %Z}")
    print(f"銘柄: {', '.join(args.tickers)}")
    print(f"period={args.period}, interval={args.interval}")
    print("=" * 72)

    frames = []
    for ticker in args.tickers:
        print(f"\n取得中: {ticker}")
        try:
            frame = fetch_one(ticker, args.period, args.interval)
        except Exception as exc:
            print(f"[ERROR] {ticker}: {type(exc).__name__}: {exc}")
            continue

        if frame.empty:
            continue

        frames.append(frame)
        latest_time = frame.index[-1]
        latest_close = frame["Close"].iloc[-1]
        latest_volume = frame["Volume"].iloc[-1] if "Volume" in frame else None

        if latest_time.tzinfo is None:
            latest_time_jst = latest_time.replace(tzinfo=JST)
        else:
            latest_time_jst = latest_time.tz_convert(JST)

        age_seconds = (now - latest_time_jst.to_pydatetime()).total_seconds()
        print(f"取得行数: {len(frame)}")
        print(f"最新バー時刻(JST): {latest_time_jst:%Y-%m-%d %H:%M:%S %Z}")
        print(f"最新Close: {latest_close}")
        print(f"最新Volume: {latest_volume}")
        print(f"実行時刻との差: {age_seconds:.0f}秒")
        print("直近5行:")
        print(frame.tail(5).to_string())

    if not frames:
        print("\n有効なデータを取得できませんでした。")
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"yfinance_jp_{now:%Y%m%d_%H%M%S}.csv"

    combined = pd.concat(frames)
    combined.to_csv(output_file, encoding="utf-8-sig")
    print("\n" + "=" * 72)
    print(f"CSV保存先: {output_file.resolve()}")
    print("注意: 最新バー時刻との差は配信遅延そのものではありません。")
    print("1分足のバー時刻・形成中バー・市場休場などの影響を受けます。")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
