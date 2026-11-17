"""Westmetall から LME 価格・在庫の履歴表を取得・解析する共通モジュール。

ページ構造（2026-11-18 に実際に取得して確認）:
- 履歴表: https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_cash&year=2025
  - year を省略すると当年分
  - 列: date / Cash-Settlement / 3-month / stock（数値はカンマ区切り、日付は "16. November 2026"）
  - 途中に見出し行（<th>）が繰り返し挟まる
"""

import csv
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.westmetall.com/en/markdaten.php"
USER_AGENT = "lme-metals-monitor/1.0 (personal use; daily LME price collection)"
REQUEST_INTERVAL = 1.5  # 秒。取得マナーとして1秒以上あける

# 金属名 → Westmetall の field 名
FIELDS = {
    "copper": "LME_Cu_cash",
    "aluminium": "LME_Al_cash",
    "nickel": "LME_Ni_cash",
    "zinc": "LME_Zn_cash",
    "tin": "LME_Sn_cash",
    "lead": "LME_Pb_cash",
}

ROOT = Path(__file__).resolve().parent.parent
PRICES_CSV = ROOT / "data" / "prices.csv"
STOCKS_CSV = ROOT / "data" / "stocks.csv"
PRICE_HEADER = ["date", "metal", "cash", "three_month"]
STOCK_HEADER = ["date", "metal", "stock"]

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
_last_request = 0.0


def _get(params):
    """リクエスト間隔を守って GET する。"""
    global _last_request
    wait = REQUEST_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    resp = _session.get(BASE_URL, params=params, timeout=30)
    _last_request = time.monotonic()
    resp.raise_for_status()
    return resp.text


def _num(text):
    """'13,375.00' → 13375.0。空や '-' は None。"""
    text = text.strip().replace(",", "")
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fetch_year(metal, year=None):
    """指定金属・年の履歴表を取得し、日付ごとの dict のリストを返す。"""
    params = {"action": "table", "field": FIELDS[metal]}
    if year is not None:
        params["year"] = year
    soup = BeautifulSoup(_get(params), "html.parser")
    rows = []
    for tr in soup.select("table tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue  # 見出し行など
        try:
            date = datetime.strptime(tds[0].get_text(strip=True), "%d. %B %Y").date()
        except ValueError:
            continue
        rows.append({
            "date": date.isoformat(),
            "metal": metal,
            "cash": _num(tds[1].get_text()),
            "three_month": _num(tds[2].get_text()),
            "stock": _num(tds[3].get_text()) if len(tds) > 3 else None,
        })
    return rows


def _fmt(v):
    if v is None:
        return ""
    return f"{v:.2f}".rstrip("0").rstrip(".")


def load_csv(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save(rows):
    """取得した行を既存CSVとマージして保存する（同じ date+metal は新しい値で上書き）。

    戻り値: (価格の新規追加件数, 在庫の新規追加件数)
    """
    prices = {(r["date"], r["metal"]): r for r in load_csv(PRICES_CSV)}
    stocks = {(r["date"], r["metal"]): r for r in load_csv(STOCKS_CSV)}
    n_price = n_stock = 0
    for r in rows:
        key = (r["date"], r["metal"])
        if r["cash"] is not None or r["three_month"] is not None:
            n_price += key not in prices
            prices[key] = {"date": r["date"], "metal": r["metal"],
                           "cash": _fmt(r["cash"]), "three_month": _fmt(r["three_month"])}
        if r["stock"] is not None:
            n_stock += key not in stocks
            stocks[key] = {"date": r["date"], "metal": r["metal"], "stock": _fmt(r["stock"])}

    PRICES_CSV.parent.mkdir(parents=True, exist_ok=True)
    for path, header, data in ((PRICES_CSV, PRICE_HEADER, prices),
                               (STOCKS_CSV, STOCK_HEADER, stocks)):
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
            w.writeheader()
            for key in sorted(data):
                w.writerow(data[key])
    return n_price, n_stock
