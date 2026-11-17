"""初回のみ：過去5年分（当年＋前5年）の価格・在庫を取得して data/ に保存する。

使い方: python scripts/backfill_prices.py [年数=5]
"""

import sys
from datetime import date

from westmetall import FIELDS, fetch_year, save


def main():
    years_back = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    this_year = date.today().year
    rows = []
    for metal in FIELDS:
        for year in range(this_year - years_back, this_year + 1):
            try:
                got = fetch_year(metal, year)
            except Exception as e:  # 1ページ失敗しても他は続ける
                print(f"[失敗] {metal} {year}: {e}", file=sys.stderr)
                continue
            print(f"{metal} {year}: {len(got)} 行")
            rows.extend(got)
    n_price, n_stock = save(rows)
    print(f"保存完了: 価格 新規{n_price}件 / 在庫 新規{n_stock}件")


if __name__ == "__main__":
    main()
