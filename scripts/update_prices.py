"""毎日：当年の履歴表（6金属 × 1ページ）を取得して最新価格を追記する。

当年の表をまるごと取り込むので、実行を休んだ日があっても欠けた日は自動で埋まる。
CSVの最新日が前年の場合（年明け直後）は前年の表も取得する。
"""

import sys
from datetime import date

from westmetall import FIELDS, PRICES_CSV, fetch_year, load_csv, save


def main():
    this_year = date.today().year
    existing = load_csv(PRICES_CSV)
    latest = max((r["date"] for r in existing), default=None)
    years = [this_year]
    if latest is None or int(latest[:4]) < this_year:
        years.insert(0, this_year - 1)

    rows, failed = [], []
    for metal in FIELDS:
        for year in years:
            try:
                got = fetch_year(metal, year)
                if not got:
                    # ページ構造が変わった可能性。黙って成功扱いにしない
                    raise ValueError("表から1行も読み取れませんでした")
                rows.extend(got)
            except Exception as e:
                print(f"[失敗] {metal} {year}: {e}", file=sys.stderr)
                failed.append(metal)

    n_price, n_stock = save(rows)
    newest = max((r["date"] for r in rows), default="なし")
    print(f"最新日: {newest} / 価格 新規{n_price}件 / 在庫 新規{n_stock}件")
    if failed:
        print(f"取得失敗: {', '.join(sorted(set(failed)))}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
