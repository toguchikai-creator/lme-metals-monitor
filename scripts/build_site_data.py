"""表示用JSON（docs/data/site_data.json）を生成する。

入力: data/prices.csv, data/stocks.csv, data/news.json
出力: 価格一覧（騰落率つき）、チャート用の時系列、セクション別のニュース
"""

import csv
import json
from bisect import bisect_right
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRICES_CSV = ROOT / "data" / "prices.csv"
STOCKS_CSV = ROOT / "data" / "stocks.csv"
NEWS_JSON = ROOT / "data" / "news.json"
OUT_JSON = ROOT / "docs" / "data" / "site_data.json"

JST = timezone(timedelta(hours=9))

# 表示順と日本語名
METALS = [
    ("copper", "銅", "Copper"),
    ("aluminium", "アルミニウム", "Aluminium"),
    ("nickel", "ニッケル", "Nickel"),
    ("zinc", "亜鉛", "Zinc"),
    ("tin", "スズ", "Tin"),
    ("lead", "鉛", "Lead"),
]

NEWS_DAYS = 7           # 画面に出すニュースの期間
NEWS_PER_SECTION = 15   # セクションごとの最大件数
IMPORTANCE_ORDER = {"高": 0, "中": 1, "低": 2}


def shift_months(d, months):
    """月単位でさかのぼる。存在しない日（3/31 → 2/31 など）は月末に丸める。"""
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12)
    return date(y, m + 1, min(d.day, monthrange(y, m + 1)[1]))


def base_dates(as_of, prev_day):
    """各期間の比較基準日。1日は前営業日、それ以外は暦でさかのぼる。"""
    return {
        "1d": prev_day,
        "1w": as_of - timedelta(days=7),
        "1m": shift_months(as_of, 1),
        "1y": shift_months(as_of, 12),
        "3y": shift_months(as_of, 36),
        "5y": shift_months(as_of, 60),
    }


def pct_change(dates, values, as_of, target):
    """基準日以前で最も近い営業日の現物価格と比べた騰落率（%）。データ不足なら None。"""
    if target is None or target < dates[0]:
        return None
    i = bisect_right(dates, target) - 1
    base = values[i]
    return round((values[-1] / base - 1) * 100, 2) if base else None


def load_prices():
    series = {key: [] for key, _, _ in METALS}
    with PRICES_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["metal"] in series and r["cash"]:
                series[r["metal"]].append((date.fromisoformat(r["date"]), float(r["cash"]),
                                           float(r["three_month"]) if r["three_month"] else None))
    for rows in series.values():
        rows.sort()
    return series


def load_stocks():
    stocks = {}
    if STOCKS_CSV.exists():
        with STOCKS_CSV.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                stocks.setdefault(r["metal"], []).append((r["date"], float(r["stock"])))
    for rows in stocks.values():
        rows.sort()
    return stocks


def build_metals(series, stocks):
    table, chart = [], {}
    for key, name_ja, name_en in METALS:
        rows = series[key]
        dates = [r[0] for r in rows]
        cash = [r[1] for r in rows]
        as_of = dates[-1]
        prev = dates[-2] if len(dates) > 1 else None
        changes = {p: pct_change(dates, cash, as_of, t) for p, t in base_dates(as_of, prev).items()}

        st = stocks.get(key, [])
        table.append({
            "key": key, "name_ja": name_ja, "name_en": name_en,
            "date": as_of.isoformat(),
            "cash": cash[-1], "three_month": rows[-1][2],
            "stock": st[-1][1] if st else None,
            "stock_change": st[-1][1] - st[-2][1] if len(st) > 1 else None,
            "changes": changes,
        })
        chart[key] = {"dates": [d.isoformat() for d in dates], "cash": cash}
    return table, chart


def build_news():
    if not NEWS_JSON.exists():
        return {"nickel": [], "nonferrous": []}
    articles = json.loads(NEWS_JSON.read_text(encoding="utf-8"))["articles"]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=NEWS_DAYS)).isoformat()
    sections = {"nickel": [], "nonferrous": []}
    for a in articles:
        if a["published"] < cutoff:
            continue
        # Claudeが付けたカテゴリを優先し、「その他」は検索クエリのセクションに入れる
        if a["category"] == "ニッケル":
            section = "nickel"
        elif a["category"] in ("銅", "アルミ"):
            section = "nonferrous"
        else:
            section = a["section"]
        sections[section].append({
            "title_ja": a["title_ja"], "summary_ja": a["summary_ja"], "title_en": a["title"],
            "source": a["source"], "link": a["link"], "published": a["published"],
            "category": a["category"], "importance": a["importance"],
        })
    for items in sections.values():
        items.sort(key=lambda a: a["published"], reverse=True)          # 新しい順
        items.sort(key=lambda a: IMPORTANCE_ORDER.get(a["importance"], 9))  # 重要度「高」を上に（安定ソート）
        del items[NEWS_PER_SECTION:]
    return sections


def main():
    table, chart = build_metals(load_prices(), load_stocks())
    data = {
        "generated_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
        "as_of": max(m["date"] for m in table),
        "metals": table,
        "chart": chart,
        "news": build_news(),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n_news = sum(len(v) for v in data["news"].values())
    print(f"出力: {OUT_JSON.relative_to(ROOT)}（{OUT_JSON.stat().st_size // 1024} KB, 基準日 {data['as_of']}, ニュース {n_news} 件）")


if __name__ == "__main__":
    main()
