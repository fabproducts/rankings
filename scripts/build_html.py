#!/usr/bin/env python3
"""data/rankings_us.csv と data/rankings_jp.csv から index.html を生成する。

各市場について、最新記録日のトップ25と前回記録日比（順位変動・売買代金変化率）を表示。
スマホ閲覧前提のレスポンシブ・日本語UI・静的HTML（外部依存なし）。
usage: python3 scripts/build_html.py
"""
import csv
import datetime
import html
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOP_N = 25

MARKETS = [
    {
        "key": "us",
        "flag": "\U0001F1FA\U0001F1F8",
        "title": "米国株",
        "csv": os.path.join(ROOT, "data", "rankings_us.csv"),
        "unit": "B$",
        "value_div": 1e9,
        "value_fmt": lambda v: f"{v / 1e9:,.1f}",
        "price_fmt": lambda p: f"${p:,.2f}",
        "note": "売買代金の単位は B$（10億ドル）。日付は米国東部時間のセッション日。",
    },
    {
        "key": "jp",
        "flag": "\U0001F1EF\U0001F1F5",
        "title": "日本株",
        "csv": os.path.join(ROOT, "data", "rankings_jp.csv"),
        "unit": "億円",
        "value_div": 1e8,
        "value_fmt": lambda v: f"{v / 1e8:,.0f}",
        "price_fmt": lambda p: f"{p:,.0f}円" if p == int(p) else f"{p:,.1f}円",
        "note": "売買代金の単位は億円。日付は日本時間のセッション日。",
    },
]

WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]


def load(path):
    if not os.path.exists(path):
        return {}
    by_date = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["rank"] = int(r["rank"])
            r["close"] = float(r["close"])
            r["change_pct"] = float(r["change_pct"])
            r["value_traded"] = float(r["value_traded"])
            by_date.setdefault(r["date"], []).append(r)
    for rows in by_date.values():
        rows.sort(key=lambda r: r["rank"])
    return by_date


def date_ja(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{iso}（{WEEKDAYS_JA[d.weekday()]}）"


def pct_cls(v):
    return "pos" if v > 0 else ("neg" if v < 0 else "flat")


def rank_move_html(code, rank, prev_ranks):
    if code not in prev_ranks:
        return '<span class="mv new">NEW</span>'
    diff = prev_ranks[code] - rank
    if diff > 0:
        return f'<span class="mv pos">&#9650;{diff}</span>'
    if diff < 0:
        return f'<span class="mv neg">&#9660;{-diff}</span>'
    return '<span class="mv flat">&#8594;</span>'


def section_html(m):
    by_date = load(m["csv"])
    if not by_date:
        return (f'<section id="{m["key"]}"><h2>{m["flag"]} {m["title"]}</h2>'
                '<p class="sub">まだ記録がありません。</p></section>')
    dates = sorted(by_date)
    latest, prev = dates[-1], (dates[-2] if len(dates) >= 2 else None)
    rows = by_date[latest][:TOP_N]
    prev_ranks, prev_values = {}, {}
    if prev:
        for r in by_date[prev]:
            prev_ranks[r["code"]] = r["rank"]
            prev_values[r["code"]] = r["value_traded"]

    trs = []
    for r in rows:
        code = html.escape(r["code"])
        name = html.escape(r["name"])
        chg = r["change_pct"]
        move = rank_move_html(r["code"], r["rank"], prev_ranks)
        if r["code"] in prev_values and prev_values[r["code"]] > 0:
            vchg = (r["value_traded"] / prev_values[r["code"]] - 1) * 100
            vchg_html = f'<span class="{pct_cls(vchg)}">{vchg:+.0f}%</span>'
        else:
            vchg_html = '<span class="flat">&#8212;</span>'
        trs.append(f"""      <tr>
        <td class="rk">{r["rank"]}</td>
        <td class="mvc">{move}</td>
        <td class="nm"><span class="code">{code}</span><br>{name}</td>
        <td class="num">{m["price_fmt"](r["close"])}<br><span class="{pct_cls(chg)}">{chg:+.2f}%</span></td>
        <td class="num">{m["value_fmt"](r["value_traded"])} <span class="unit">{m["unit"]}</span><br>{vchg_html}</td>
      </tr>""")

    prev_txt = f"　｜　前回比: {date_ja(prev)}" if prev else ""
    return f"""  <section id="{m["key"]}">
    <h2>{m["flag"]} {m["title"]} 売買代金トップ{TOP_N}</h2>
    <p class="sub">対象日 {date_ja(latest)}{prev_txt}　｜　記録 {len(dates)}日分（{dates[0]}〜{latest}）</p>
    <div class="tablewrap">
    <table class="rank-table">
      <thead><tr>
        <th class="rk">#</th><th>変動</th><th class="left">銘柄</th>
        <th>株価 / 前日比</th><th>売買代金 / 前回比</th>
      </tr></thead>
      <tbody>
{os.linesep.join(trs)}
      </tbody>
    </table>
    </div>
    <p class="note">{m["note"]}</p>
  </section>"""


def main():
    # 注意: 出力は入力CSVに対して決定的にする（生成時刻等を埋め込まない）。
    # データ不変ならHTMLも不変となり、workflowの「変更なしなら commit しない」ガードが機能する。
    sections = os.linesep.join(section_html(m) for m in MARKETS)
    page = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>日米 株式売買代金ランキング</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Hiragino Sans','Yu Gothic',sans-serif;
         background:#0f1117; color:#e2e8f0; padding:16px; max-width:760px; margin:0 auto; }}
  h1 {{ font-size:20px; color:#f8fafc; margin:8px 0 4px; }}
  .lead {{ font-size:12px; color:#64748b; margin-bottom:14px; line-height:1.6; }}
  nav {{ display:flex; gap:10px; margin-bottom:18px; }}
  nav a {{ font-size:13px; color:#93c5fd; text-decoration:none; padding:6px 12px;
          background:#1a2035; border-radius:6px; }}
  h2 {{ font-size:16px; color:#f1f5f9; margin:26px 0 4px; }}
  .sub {{ font-size:11px; color:#64748b; margin-bottom:10px; line-height:1.6; }}
  .tablewrap {{ overflow-x:auto; }}
  table {{ border-collapse:collapse; font-size:13px; width:100%; }}
  th {{ text-align:right; padding:6px 8px; font-size:11px; color:#475569;
       border-bottom:2px solid #2d3748; white-space:nowrap; }}
  th.left {{ text-align:left; }}
  th.rk {{ text-align:right; width:28px; }}
  td {{ padding:7px 8px; text-align:right; white-space:nowrap;
       border-bottom:1px solid #1a202c; color:#cbd5e1; vertical-align:middle;
       font-variant-numeric:tabular-nums; line-height:1.5; }}
  tr:hover td {{ background:#1a2035; }}
  td.rk {{ color:#64748b; font-weight:700; }}
  td.mvc {{ text-align:center; }}
  td.nm {{ text-align:left; color:#e2e8f0; font-weight:600; white-space:normal;
          min-width:130px; font-size:12px; line-height:1.4; }}
  td.nm .code {{ font-family:'SF Mono',ui-monospace,monospace; color:#94a3b8; font-size:11px; font-weight:600; }}
  td.num {{ font-size:12px; }}
  .unit {{ color:#64748b; font-size:10px; }}
  .pos {{ color:#4ade80; font-weight:600; }}
  .neg {{ color:#f87171; font-weight:600; }}
  .flat {{ color:#64748b; }}
  .mv {{ font-size:11px; font-weight:700; padding:2px 6px; border-radius:4px; }}
  .mv.pos {{ background:rgba(74,222,128,0.12); color:#4ade80; }}
  .mv.neg {{ background:rgba(248,113,113,0.12); color:#f87171; }}
  .mv.new {{ background:rgba(96,165,250,0.15); color:#60a5fa; }}
  .mv.flat {{ color:#475569; }}
  .note {{ font-size:11px; color:#475569; margin-top:8px; line-height:1.6; }}
  footer {{ font-size:11px; color:#475569; margin:30px 0 10px; line-height:1.8; }}
  footer a {{ color:#64748b; }}
</style>
</head>
<body>
  <h1>日米 株式売買代金ランキング</h1>
  <p class="lead">各市場の売買代金（Value Traded）上位{TOP_N}銘柄を毎営業日に自動記録。
「変動」は前回記録日からの順位変動、売買代金の下段は前回記録日比の変化率。</p>
  <nav><a href="#us">&#127482;&#127480; 米国株</a><a href="#jp">&#127471;&#127477; 日本株</a></nav>
{sections}
  <footer>
    データソース: TradingView スクリーナー（非公式API）。休場日・取得障害時は記録をスキップします。<br>
    <a href="https://github.com/fabproducts/rankings">GitHub: fabproducts/rankings</a>
  </footer>
</body>
</html>
"""
    out = os.path.join(ROOT, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"index.html を生成しました: {out}")


if __name__ == "__main__":
    main()
