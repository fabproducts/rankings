#!/usr/bin/env python3
"""data/rankings_us.csv と data/rankings_jp.csv から index.html を生成する。

このページの価値は「今日のランキング」ではなく「日次の横並び推移からお祭り開始銘柄を早く見つける」こと。
各市場について以下を生成する:
  - 本日のシグナル（ページ上部サマリー）: 新規ランクイン / 売買代金急増(+50%超) / 順位急上昇(10位以上)
  - 最新記録日のトップ25と前回記録日比（順位変動・売買代金変化率、シグナル該当は強調表示）
  - 順位推移ヒートマップ（直近14記録日 × 最新上位25銘柄、色 = 順位の濃淡）

スマホ閲覧前提のレスポンシブ・日本語UI・静的HTML（外部依存なし）。
出力は入力CSVに対して決定的（生成時刻等を埋め込まない）。
usage: python3 scripts/build_html.py
"""
import csv
import datetime
import html
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOP_N = 25
HEAT_DAYS = 14          # ヒートマップに出す直近記録日数
SURGE_PCT = 50.0        # 売買代金急増と判定する前回比(%)の閾値
JUMP_RANKS = 10         # 順位急上昇と判定するジャンプ幅(順位)の閾値

MARKETS = [
    {
        "key": "us",
        "flag": "\U0001F1FA\U0001F1F8",
        "title": "米国株",
        "csv": os.path.join(ROOT, "data", "rankings_us.csv"),
        "unit": "B$",
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


def rank_tier(rank):
    """ヒートマップの色階級。上位ほど濃い緑。"""
    if rank is None:
        return "t-none"
    if rank <= 5:
        return "t5"
    if rank <= 10:
        return "t10"
    if rank <= 25:
        return "t25"
    return "t50"  # JP過去データは50位まで記録がある


def analyze(m):
    """CSVを読み、最新日トップ25・前回比・シグナルを計算して返す。"""
    by_date = load(m["csv"])
    a = {"by_date": by_date, "dates": sorted(by_date), "rows": [],
         "latest": None, "prev": None, "prev_ranks": {}, "prev_values": {},
         "signals": []}
    if not by_date:
        return a
    dates = a["dates"]
    a["latest"] = dates[-1]
    a["prev"] = dates[-2] if len(dates) >= 2 else None
    a["rows"] = by_date[a["latest"]][:TOP_N]
    if a["prev"]:
        for r in by_date[a["prev"]]:
            a["prev_ranks"][r["code"]] = r["rank"]
            a["prev_values"][r["code"]] = r["value_traded"]

    if not a["prev"]:
        return a
    for r in a["rows"]:
        code = r["code"]
        badges, details = [], []
        prev_rank = a["prev_ranks"].get(code)
        prev_val = a["prev_values"].get(code, 0)
        vchg = (r["value_traded"] / prev_val - 1) * 100 if prev_val > 0 else None
        if prev_rank is None:
            badges.append(("new", "新規IN"))
            details.append(f'前回圏外 &#8594; {r["rank"]}位')
        elif prev_rank - r["rank"] >= JUMP_RANKS:
            badges.append(("jump", f"&#9650;{prev_rank - r['rank']}"))
            details.append(f'{prev_rank}位 &#8594; {r["rank"]}位')
        if vchg is not None and vchg > SURGE_PCT:
            badges.append(("surge", "代金急増"))
            details.append(f'売買代金 前回比 {vchg:+.0f}%'
                           f'（{m["value_fmt"](prev_val)} &#8594; {m["value_fmt"](r["value_traded"])} {m["unit"]}）')
        if badges:
            a["signals"].append({"row": r, "badges": badges, "details": details, "vchg": vchg})
    return a


def signals_block_html(results):
    """ページ上部の「本日のシグナル」サマリー欄。"""
    lines = []
    for m, a in results:
        if not a["dates"]:
            continue
        if not a["prev"]:
            lines.append(f'<li class="none">{m["flag"]} {m["title"]}: 記録が1日分のみのため判定できません</li>')
            continue
        if not a["signals"]:
            lines.append(f'<li class="none">{m["flag"]} {m["title"]}（{a["latest"]}）: シグナルなし</li>')
            continue
        for s in a["signals"]:
            r = s["row"]
            badges = "".join(f'<span class="sb {cls}">{label}</span>' for cls, label in s["badges"])
            code = html.escape(r["code"])
            name = html.escape(r["name"])
            detail = "　".join(s["details"])
            lines.append(
                f'<li>{m["flag"]} {badges} <span class="code">{code}</span> '
                f'<strong>{name}</strong><br><span class="detail">{detail}</span></li>')
    body = os.linesep.join(lines) if lines else '<li class="none">記録がありません</li>'
    return f"""  <section id="signals" class="signals">
    <h2>&#128680; 本日のシグナル</h2>
    <p class="sub">新規ランクイン（前回圏外 &#8594; 上位{TOP_N}入り）・売買代金の急増（前回比+{SURGE_PCT:.0f}%超）・順位の急上昇（{JUMP_RANKS}位以上ジャンプ）を自動検知。
お祭りの初動をランキング推移から拾うための欄です。</p>
    <ul>
{body}
    </ul>
  </section>"""


def rank_move_html(code, rank, prev_ranks, is_jump):
    if code not in prev_ranks:
        return '<span class="mv new">NEW</span>'
    diff = prev_ranks[code] - rank
    if diff > 0:
        cls = "mv pos jump" if is_jump else "mv pos"
        return f'<span class="{cls}">&#9650;{diff}</span>'
    if diff < 0:
        return f'<span class="mv neg">&#9660;{-diff}</span>'
    return '<span class="mv flat">&#8594;</span>'


def heatmap_html(m, a):
    """順位推移ヒートマップ（直近HEAT_DAYS記録日 × 最新上位TOP_N銘柄）。"""
    dates = a["dates"][-HEAT_DAYS:]
    if len(dates) < 2:
        return ""
    codes = [r["code"] for r in a["rows"]]
    name_of = {r["code"]: r["name"] for r in a["rows"]}
    head = "".join(f'<th class="gd">{d[5:].replace("-", "/")}</th>' for d in dates)
    trs = []
    for code in codes:
        cells = []
        for d in dates:
            rec = next((r for r in a["by_date"][d] if r["code"] == code), None)
            rank = rec["rank"] if rec else None
            cells.append(f'<td class="{rank_tier(rank)}">{rank if rank else "&#183;"}</td>')
        code_e = html.escape(code)
        name_e = html.escape(name_of[code])
        trs.append(f'      <tr><th class="gnm"><span class="code">{code_e}</span> {name_e}</th>'
                   + "".join(cells) + "</tr>")
    body = os.linesep.join(trs)
    t50_legend = ('<span><i class="t50"></i>26&#8211;50位</span>'
                  if 'class="t50"' in body else "")
    legend = ('<span><i class="t5"></i>1&#8211;5位</span>'
              '<span><i class="t10"></i>6&#8211;10位</span>'
              '<span><i class="t25"></i>11&#8211;25位</span>'
              f'{t50_legend}'
              '<span><i class="t-none"></i>圏外</span>')
    return f"""    <h3>順位推移ヒートマップ（直近{len(dates)}記録日 &#215; 最新上位{len(codes)}銘柄）</h3>
    <p class="sub">上位に張り付き続ける銘柄・突然浮上した銘柄が一目で分かります。横スクロールできます。</p>
    <div class="tablewrap">
    <table class="heat">
      <thead><tr><th class="gnm">銘柄</th>{head}</tr></thead>
      <tbody>
{body}
      </tbody>
    </table>
    </div>
    <div class="legend">{legend}</div>"""


def section_html(m, a):
    if not a["dates"]:
        return (f'<section id="{m["key"]}"><h2>{m["flag"]} {m["title"]}</h2>'
                '<p class="sub">まだ記録がありません。</p></section>')
    dates = a["dates"]
    latest, prev = a["latest"], a["prev"]
    signal_codes = {s["row"]["code"] for s in a["signals"]}
    jump_codes = {s["row"]["code"] for s in a["signals"]
                  if any(cls == "jump" for cls, _ in s["badges"])}
    surge_codes = {s["row"]["code"] for s in a["signals"]
                   if any(cls == "surge" for cls, _ in s["badges"])}

    trs = []
    for r in a["rows"]:
        code = html.escape(r["code"])
        name = html.escape(r["name"])
        chg = r["change_pct"]
        move = rank_move_html(r["code"], r["rank"], a["prev_ranks"], r["code"] in jump_codes)
        prev_val = a["prev_values"].get(r["code"], 0)
        if prev_val > 0:
            vchg = (r["value_traded"] / prev_val - 1) * 100
            vcls = pct_cls(vchg) + (" surge" if r["code"] in surge_codes else "")
            vchg_html = f'<span class="{vcls}">{vchg:+.0f}%</span>'
        else:
            vchg_html = '<span class="flat">&#8212;</span>'
        row_cls = ' class="sig"' if r["code"] in signal_codes else ""
        trs.append(f"""      <tr{row_cls}>
        <td class="rk">{r["rank"]}<br>{move}</td>
        <td class="nm"><span class="code">{code}</span><br>{name}</td>
        <td class="num">{m["value_fmt"](r["value_traded"])} <span class="unit">{m["unit"]}</span><br>{vchg_html}</td>
        <td class="num">{m["price_fmt"](r["close"])}<br><span class="{pct_cls(chg)}">{chg:+.2f}%</span></td>
      </tr>""")

    prev_txt = f"　｜　前回比: {date_ja(prev)}" if prev else ""
    return f"""  <section id="{m["key"]}">
    <h2>{m["flag"]} {m["title"]} 売買代金トップ{TOP_N}</h2>
    <p class="sub">対象日 {date_ja(latest)}{prev_txt}　｜　記録 {len(dates)}日分（{dates[0]}〜{latest}）</p>
    <div class="tablewrap">
    <table class="rank-table">
      <thead><tr>
        <th class="rk">#</th><th class="left">銘柄</th>
        <th>売買代金 / 前回比</th><th>株価 / 前日比</th>
      </tr></thead>
      <tbody>
{os.linesep.join(trs)}
      </tbody>
    </table>
    </div>
{heatmap_html(m, a)}
    <p class="note">{m["note"]}</p>
  </section>"""


def main():
    # 注意: 出力は入力CSVに対して決定的にする（生成時刻等を埋め込まない）。
    # データ不変ならHTMLも不変となり、workflowの「変更なしなら commit しない」ガードが機能する。
    results = [(m, analyze(m)) for m in MARKETS]
    signals = signals_block_html(results)
    sections = os.linesep.join(section_html(m, a) for m, a in results)
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
  h3 {{ font-size:14px; color:#e2e8f0; margin:22px 0 4px; }}
  .sub {{ font-size:11px; color:#64748b; margin-bottom:10px; line-height:1.6; }}
  .tablewrap {{ overflow-x:auto; -webkit-overflow-scrolling:touch; }}
  table {{ border-collapse:collapse; font-size:13px; width:100%; }}
  th {{ text-align:right; padding:6px 8px; font-size:11px; color:#475569;
       border-bottom:2px solid #2d3748; white-space:nowrap; }}
  th.left {{ text-align:left; }}
  th.rk {{ text-align:right; width:28px; }}
  td {{ padding:7px 6px; text-align:right; white-space:nowrap;
       border-bottom:1px solid #1a202c; color:#cbd5e1; vertical-align:middle;
       font-variant-numeric:tabular-nums; line-height:1.5; }}
  tr:hover td {{ background:#1a2035; }}
  td.rk {{ color:#64748b; font-weight:700; text-align:center; }}
  td.nm {{ text-align:left; color:#e2e8f0; font-weight:600; white-space:normal;
          min-width:110px; font-size:12px; line-height:1.4; }}
  .code {{ font-family:'SF Mono',ui-monospace,monospace; color:#94a3b8; font-size:11px; font-weight:600; }}
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
  .mv.jump {{ background:#facc15; color:#0f1117; }}
  .pos.surge {{ background:#facc15; color:#0f1117; padding:1px 5px; border-radius:4px; font-weight:700; }}
  tr.sig td {{ background:rgba(250,204,21,0.06); }}
  tr.sig td:first-child {{ box-shadow:inset 3px 0 0 #facc15; }}
  tr.sig:hover td {{ background:rgba(250,204,21,0.12); }}
  .signals {{ background:#161b2b; border:1px solid #2d3748; border-radius:10px;
             padding:14px 16px 12px; margin:18px 0 6px; }}
  .signals h2 {{ margin:0 0 6px; font-size:15px; }}
  .signals ul {{ list-style:none; }}
  .signals li {{ font-size:13px; padding:8px 0; border-bottom:1px solid #1f2637; line-height:1.6; }}
  .signals li:last-child {{ border-bottom:none; }}
  .signals li.none {{ color:#64748b; font-size:12px; }}
  .signals .detail {{ font-size:11px; color:#94a3b8; }}
  .sb {{ display:inline-block; font-size:11px; font-weight:700; padding:2px 7px;
        border-radius:4px; margin-right:4px; }}
  .sb.new {{ background:#2563eb; color:#fff; }}
  .sb.jump {{ background:#facc15; color:#0f1117; }}
  .sb.surge {{ background:#f97316; color:#fff; }}
  .heat {{ font-size:11px; width:auto; }}
  .heat th.gd {{ text-align:center; min-width:34px; padding:5px 4px; font-weight:500; }}
  .heat th.gnm {{ text-align:left; font-size:11px; color:#cbd5e1; font-weight:600;
                 max-width:150px; min-width:120px; overflow:hidden; text-overflow:ellipsis;
                 white-space:nowrap; position:sticky; left:0; background:#0f1117;
                 border-bottom:1px solid #1a202c; padding:4px 8px 4px 0; }}
  .heat thead th.gnm {{ border-bottom:2px solid #2d3748; }}
  .heat td {{ text-align:center; padding:4px 4px; color:#0f1117; font-weight:700;
             border-bottom:1px solid #0f1117; font-size:10px; }}
  .heat td.t5 {{ background:#15803d; color:#f0fdf4; }}
  .heat td.t10 {{ background:#4ade80; }}
  .heat td.t25 {{ background:#bbf7d0; }}
  .heat td.t50 {{ background:#374151; color:#9ca3af; font-weight:500; }}
  .heat td.t-none {{ background:#1a202c; color:#374151; font-weight:400; }}
  .legend {{ font-size:11px; color:#64748b; margin-top:8px; display:flex; gap:14px;
            flex-wrap:wrap; align-items:center; }}
  .legend span {{ display:inline-flex; align-items:center; gap:5px; }}
  .legend i {{ width:13px; height:13px; border-radius:3px; display:inline-block; }}
  .legend i.t5 {{ background:#15803d; }}
  .legend i.t10 {{ background:#4ade80; }}
  .legend i.t25 {{ background:#bbf7d0; }}
  .legend i.t50 {{ background:#374151; }}
  .legend i.t-none {{ background:#1a202c; border:1px solid #2d3748; }}
  .note {{ font-size:11px; color:#475569; margin-top:8px; line-height:1.6; }}
  footer {{ font-size:11px; color:#475569; margin:30px 0 10px; line-height:1.8; }}
  footer a {{ color:#64748b; }}
</style>
</head>
<body>
  <h1>日米 株式売買代金ランキング</h1>
  <p class="lead">各市場の売買代金（Value Traded）上位{TOP_N}銘柄を毎営業日に自動記録。
その日のランキングだけでなく、日次の横並び推移から資金流入の初動（お祭り開始銘柄）を検知します。</p>
  <nav><a href="#us">&#127482;&#127480; 米国株</a><a href="#jp">&#127471;&#127477; 日本株</a></nav>
{signals}
{sections}
  <footer>
    データソース: TradingView スクリーナー（非公式API）。休場日・取得障害時は記録をスキップします。<br>
    <a href="https://github.com/fabproducts/rankings">GitHub: fabproducts/rankings</a>
  </footer>
  <script>
    // ヒートマップは初期表示で最新日（右端）が見えるようにスクロールしておく
    document.querySelectorAll(".tablewrap").forEach(function (w) {{
      if (w.querySelector("table.heat")) {{ w.scrollLeft = w.scrollWidth; }}
    }});
  </script>
</body>
</html>
"""
    out = os.path.join(ROOT, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"index.html を生成しました: {out}")


if __name__ == "__main__":
    main()
