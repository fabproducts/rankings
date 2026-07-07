# 日米 株式売買代金ランキング

日米の株式売買代金（Value Traded）ランキング上位25銘柄を、GitHub Actions で毎営業日に自動記録・公開しています。

**閲覧ページ: https://fabproducts.github.io/rankings/**

## 仕組み

- データソース: TradingView スクリーナーAPI（`scanner.tradingview.com/{america,japan}/scan`、非公式）
- スケジュール（GitHub Actions cron・UTC）
  - 米国: 平日 22:00 UTC（= 翌朝 7:00 JST、米国市場クローズ後）
  - 日本: 平日 07:00 UTC（= 16:00 JST、東京市場クローズ後）
- 手動実行: Actions の `record` workflow から `workflow_dispatch`（market: us / jp / both）

## ファイル構成

- `data/rankings_us.csv` … 米国株の日次記録（日付は米国東部時間のセッション日）
- `data/rankings_jp.csv` … 日本株の日次記録（日付は日本時間のセッション日）
- `scripts/record.py` … ランキング取得・CSV追記（冪等: 同一セッション日は再記録しない。休場日は前回とデータ同一のためスキップ）
- `scripts/build_html.py` … CSV から `index.html` を生成
- `.github/workflows/record.yml` … 日次実行ワークフロー

## CSVフォーマット

`date,rank,code,name,close,change_pct,value_traded`

- `close` … 終値（米国はドル、日本は円）
- `change_pct` … 前日比（%）
- `value_traded` … 売買代金（米国はドル、日本は円の生値）

## 注意

- 市場が開いている時間帯に手動実行すると、その時点までの途中経過スナップショットが記録されます（通常はクローズ後の定時実行に任せてください）
- 非公式APIのため、仕様変更等で取得できなくなる可能性があります。取得件数が想定を下回る場合は記録せず異常終了します
