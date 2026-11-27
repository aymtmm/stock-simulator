# yfinance 日本株・分足データ取得テスト

今回の目的は、yfinance経由で日本株の1分足データを取得できるか、取得時刻やデータの鮮度を確認することです。

## 取得対象

初期設定では次の3銘柄です。

- `7203.T` トヨタ自動車
- `6758.T` ソニーグループ
- `9984.T` ソフトバンクグループ

銘柄コードはYahoo!ファイナンス形式で指定します。

## 実行環境

- Windows 10/11
- Python 3.10以上
- Excel不要

## セットアップ（PowerShell）

```powershell
cd yfinance_jp_test
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

To also save retrieved OHLCV bars into the SQLite database, install the core
project into the same environment:

```powershell
pip install -e ..\tool
```

実行ポリシーで止まる場合は、同じPowerShellで一時的に次を実行してから再度Activateしてください。

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 実行

```powershell
python fetch_yfinance.py
```

銘柄を指定する場合：

```powershell
python fetch_yfinance.py --tickers 7203.T 6758.T
```

5分足を試す場合：

```powershell
python fetch_yfinance.py --interval 5m --period 5d
```

SQLiteへの保存は明示的に有効にします。未指定の場合、従来どおりCSVだけを
出力します。

```powershell
python fetch_yfinance.py --interval 1m --save-to-db
python fetch_yfinance.py --tickers 7203.T 6758.T --interval 5m --save-to-db --db ..\tool\data\database\market.sqlite3
```

The default mapping file is [`symbol_mappings.csv`](./symbol_mappings.csv), with
columns `source,source_symbol,symbol`. Add an explicit row before importing a new
ticker, or pass another file with `--symbol-map`. A missing mapping aborts the
entire database batch; it is never converted by stripping `.T` or by using the
source ticker as an implicit internal symbol.

保存対象は分足のみです。OHLCは`auto_adjust=False`の値として保存し、
`Adj Close`は独立した`adjusted_close`列に保存します。タイムゾーンのない
バー時刻は拒否し、時刻はUTCに正規化します。取得結果を銘柄・データ元・時間足・
価格調整基準ごとに時刻順で確認し、次のバー開始時刻が現在バーの開始＋時間足
以降の場合に、現在バーを確定として扱います。取得結果の最後のバーは、取得時刻に
かかわらず未確定です。DB内の未確定バーも後続バーで確認できれば確定に更新します。

yfinanceから確定フラグは得られないため、この状態は「後続バーにより予定区間の
終了を確認済み」という意味です。取得元による後日の訂正が
ないことまでは保証しません。より新しい取得結果の価格・出来高訂正は反映しますが、
確定状態は未確定へ戻りません。古い取得結果は新しい値を上書きせず、取得されなかった
バーも削除しません。

## 出力

`output` フォルダにCSVを保存します。標準出力には以下を表示します。

- 取得実行時刻（JST）
- 銘柄ごとの取得件数
- 最新バーの時刻
- 最新Close / Volume
- 実行時刻と最新バー時刻の差
- 直近5行

`--save-to-db`を指定した場合はSQLite処理対象バー数とDBパスも表示します。

## 確認してほしいこと

1. セットアップと実行がエラーなく完了するか
2. 3銘柄それぞれでデータが取得できるか
3. `最新バー時刻` と `実行時刻との差` がどう表示されるか
4. CSVが生成され、Excelやテキストエディタで開けるか
5. 可能なら東証の取引時間中（平日9:00〜11:30、12:30〜15:30）にも実行して、結果を比較する

## 注意点

- yfinanceはYahoo!ファイナンスの公式APIではありません。仕様変更、取得制限、欠損、取得失敗が起こる可能性があります。
- 1分足の時刻は通常バーの開始時刻を示します。表示された時刻との差を、そのまま配信遅延と断定しないでください。
- 取引時間外や休場日は、最新データが古いのが正常な場合があります。
- これは取得可否を調べるためのテストです。リアルタイム性・利用条件・データ品質が確認できるまでは、実売買判断には使わないでください。
- yfinance / Yahoo!の利用規約やデータ利用条件を確認し、許可された範囲で利用してください。
