#!/usr/bin/env python3
"""日米の株式売買代金ランキング上位25件を取得し、CSVへ日次追記する。

データソース: TradingView スクリーナーAPI（POST、売買代金 Value.Traded 降順）
usage: python3 scripts/record.py us|jp

冪等性:
- 対象セッション日が既にCSVに記録済みなら何もせず正常終了（exit 0）
- 取得データが前回記録と完全一致（休場日＝スクリーナーが前営業日の値を返す）なら記録せず正常終了
品質ガード:
- 取得件数が MIN_ROWS 未満なら取得障害と判断して記録せず異常終了（exit 1）
"""
import csv
import datetime
import json
import os
import sys
import urllib.request
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

TOP_N = 25
MIN_ROWS = 20  # これ未満しか取れなければ取得障害とみなす

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

MARKETS = {
    "us": {
        "url": "https://scanner.tradingview.com/america/scan",
        "market": "america",
        "tz": "America/New_York",
        "open": (9, 30),   # 現地の寄付き時刻。これより前なら前営業日をセッション日とする
        "csv": os.path.join(ROOT, "data", "rankings_us.csv"),
    },
    "jp": {
        "url": "https://scanner.tradingview.com/japan/scan",
        "market": "japan",
        "tz": "Asia/Tokyo",
        "open": (9, 0),
        "csv": os.path.join(ROOT, "data", "rankings_jp.csv"),
    },
}

HEADER = ["date", "rank", "code", "name", "close", "change_pct", "value_traded"]


def session_date(cfg):
    """対象セッション日を返す。現地時刻が寄付き前なら前営業日、週末は直前の金曜に丸める。"""
    now = datetime.datetime.now(ZoneInfo(cfg["tz"]))
    d = now.date()
    if (now.hour, now.minute) < cfg["open"]:
        d -= datetime.timedelta(days=1)
    while d.weekday() >= 5:  # Sat/Sun
        d -= datetime.timedelta(days=1)
    return d.isoformat()


def fetch(cfg):
    body = json.dumps({
        "columns": ["name", "description", "close", "change", "volume", "Value.Traded"],
        "sort": {"sortBy": "Value.Traded", "sortOrder": "desc"},
        "range": [0, TOP_N],
        "markets": [cfg["market"]],
        "filter": [{"left": "type", "operation": "equal", "right": "stock"}],
    }).encode("utf-8")
    req = urllib.request.Request(
        cfg["url"], data=body,
        headers={"Content-Type": "application/json", "User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    rows = []
    for i, item in enumerate(payload.get("data", []), start=1):
        code, name, close, change, volume, value = item["d"]
        if close is None or value is None:
            continue
        rows.append({
            "rank": i,
            "code": code,
            "name": name,
            "close": round(float(close), 4),
            "change_pct": round(float(change), 2) if change is not None else 0.0,
            "value_traded": int(round(float(value))),
        })
    return rows


def read_existing(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in MARKETS:
        print("usage: record.py us|jp", file=sys.stderr)
        return 2
    market = sys.argv[1]
    cfg = MARKETS[market]
    date = session_date(cfg)

    existing = read_existing(cfg["csv"])
    if any(r["date"] == date for r in existing):
        print(f"[{market}] {date} は記録済み。スキップ（正常終了）")
        return 0

    rows = fetch(cfg)
    if len(rows) < MIN_ROWS:
        print(f"[{market}] 取得 {len(rows)} 件 < {MIN_ROWS} 件。取得障害と判断し記録を中止", file=sys.stderr)
        return 1

    # 休場ガード: 直前の記録日とデータが完全一致なら、市場が動いていない（休場）とみなす
    if existing:
        last_date = existing[-1]["date"]
        last_rows = [(r["code"], r["value_traded"]) for r in existing if r["date"] == last_date]
        new_rows = [(r["code"], str(r["value_traded"])) for r in rows]
        if new_rows == last_rows[:len(new_rows)]:
            print(f"[{market}] 取得データが前回記録（{last_date}）と同一。休場とみなしスキップ（正常終了）")
            return 0

    os.makedirs(os.path.dirname(cfg["csv"]), exist_ok=True)
    is_new = not os.path.exists(cfg["csv"])
    with open(cfg["csv"], "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(HEADER)
        for r in rows:
            w.writerow([date, r["rank"], r["code"], r["name"],
                        r["close"], r["change_pct"], r["value_traded"]])
    print(f"[{market}] {date} を記録（{len(rows)}件）。トップ3: "
          + " / ".join(f"{r['code']} {r['name']}" for r in rows[:3]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
