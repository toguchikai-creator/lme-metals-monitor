"""毎日：Google News RSS から英語ニュースを集め、Claude API で日本語に翻訳・要約する。

RSSの構造（2026-11-18 に実際に取得して確認）:
- URL: https://news.google.com/rss/search?q=<クエリ>&hl=en-US&gl=US&ceid=US:en
- クエリに "when:2d" を付けると直近48時間に絞れる
- 各記事: title は「見出し - 媒体名」、link は Google のリダイレクトURL、
  source に媒体名とドメイン、published は RFC822 形式
- description はリンクだけで本文の抜粋は入っていない → 翻訳・要約は見出しから行う

使い方:
  python scripts/fetch_news.py              # 取得＋翻訳（最大20件）
  python scripts/fetch_news.py --limit 5    # 翻訳件数を絞って試す
  python scripts/fetch_news.py --dry-run    # 取得と重複除去だけ（APIを呼ばない）
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote_plus

import anthropic
import feedparser
import requests

ROOT = Path(__file__).resolve().parent.parent
NEWS_JSON = ROOT / "data" / "news.json"

USER_AGENT = "lme-metals-monitor/1.0 (personal use; daily news collection)"
RSS_URL = "https://news.google.com/rss/search?q={q}+when:2d&hl=en-US&gl=US&ceid=US:en"
REQUEST_INTERVAL = 1.5  # 秒

# セクション → 検索クエリ
QUERIES = {
    "nickel": ["LME nickel", "nickel price stainless"],
    "nonferrous": ["LME copper", "LME aluminium", "copper price", "aluminium price"],
}

MODEL = "claude-haiku-5-5"
MAX_TRANSLATE = 20      # 1日の翻訳上限（APIコスト管理）
MAX_AGE_HOURS = 48      # これより古い記事は対象外
KEEP_DAYS = 30          # キャッシュに残す日数
TITLE_SIMILARITY = 0.85  # これ以上似た見出しは同じ記事とみなす
# 見出しにどれも含まれない記事は金属と無関係とみなし、翻訳しない（APIコスト節約）
KEYWORDS = ("nickel", "copper", "alumin", "stainless", "zinc", "tin ", "metal", "lme", "smelter", "mining")

SYSTEM_PROMPT = """あなたは非鉄金属市場の記事を日本の読者向けに翻訳する編集者です。
読者はステンレス・非鉄金属の取引に関わる日本の実務担当者です。
英語ニュースの見出しと媒体名が渡されるので、記事ごとに次を返してください。

- title_ja: 自然な日本語の見出し。固有名詞・数値・単位は正確に残す
- summary_ja: 2〜3文の日本語要約。見出しから読み取れる事実と、それが価格・需給にとって持つ意味を書く。
  見出しにない数値や出来事を作らない。推測を書くときは「〜とみられる」など推測とわかる書き方にする
- category: 主な対象金属。ニッケル / 銅 / アルミ / その他 のいずれか（ステンレスはニッケルに含める）
- importance: LME価格や需給への影響の大きさ。高 / 中 / 低
  高 = 価格の大きな変動、主要国の政策・関税、大手鉱山や製錬所の供給障害など
  中 = 通常の市況記事、地域の需給動向
  低 = 個別企業の小さな話題、金属との関係が薄い記事"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title_ja": {"type": "string"},
                    "summary_ja": {"type": "string"},
                    "category": {"type": "string", "enum": ["ニッケル", "銅", "アルミ", "その他"]},
                    "importance": {"type": "string", "enum": ["高", "中", "低"]},
                },
                "required": ["id", "title_ja", "summary_ja", "category", "importance"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def load_dotenv():
    """ローカル実行用：.env（gitignore済み）があれば環境変数に読み込む。
    GitHub Actions では Secrets から環境変数が渡るので .env は不要。"""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


def article_id(link):
    return hashlib.sha1(link.encode("utf-8")).hexdigest()[:16]


def split_title(raw, source):
    """「見出し - 媒体名」から媒体名を外す。"""
    suffix = f" - {source}"
    return raw[: -len(suffix)] if source and raw.endswith(suffix) else raw


def fetch_feed(section, query):
    url = RSS_URL.format(q=quote_plus(query))
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    out = []
    for e in feed.entries:
        if not e.get("published_parsed"):
            continue
        published = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
        source = (e.get("source") or {}).get("title", "")
        out.append({
            "id": article_id(e.link),
            "title": split_title(e.title, source),
            "link": e.link,
            "source": source,
            "published": published.isoformat(),
            "section": section,
            "query": query,
        })
    return out


def similar(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= TITLE_SIMILARITY


def dedupe(articles, known_titles):
    """URL（id）と見出しの類似で重複を除く。known_titles はキャッシュ済みの見出し。"""
    seen_ids, kept_titles, result = set(), list(known_titles), []
    for a in articles:
        if a["id"] in seen_ids or any(similar(a["title"], t) for t in kept_titles):
            continue
        seen_ids.add(a["id"])
        kept_titles.append(a["title"])
        result.append(a)
    return result


def pick(articles, limit):
    """セクションごとに新しい順に並べ、交互に取り出す（片方に偏らないように）。"""
    queues = {s: sorted([a for a in articles if a["section"] == s],
                        key=lambda a: a["published"], reverse=True) for s in QUERIES}
    chosen = []
    while len(chosen) < limit and any(queues.values()):
        for s in QUERIES:
            if queues[s] and len(chosen) < limit:
                chosen.append(queues[s].pop(0))
    return chosen


def translate(articles):
    """1回のAPI呼び出しでまとめて翻訳する。戻り値: id → 翻訳結果。"""
    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY を環境変数から読む
    lines = [json.dumps({"id": a["id"], "title": a["title"], "source": a["source"]},
                        ensure_ascii=False) for a in articles]
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        output_config={"effort": "medium", "format":{"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        messages=[{"role": "user", "content": "次の記事を翻訳してください（1行1記事のJSON）。\n\n" + "\n".join(lines)}],
    )
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"翻訳が途中で止まりました: stop_reason={response.stop_reason}")
    text = next(b.text for b in response.content if b.type == "text")
    u = response.usage
    print(f"API使用量: 入力 {u.input_tokens} / 出力 {u.output_tokens} トークン")
    return {item["id"]: item for item in json.loads(text)["items"]}


def load_cache():
    if NEWS_JSON.exists():
        return json.loads(NEWS_JSON.read_text(encoding="utf-8"))
    return {"updated_at": None, "articles": []}


def save_cache(cache):
    NEWS_JSON.parent.mkdir(parents=True, exist_ok=True)
    NEWS_JSON.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=MAX_TRANSLATE, help="翻訳する最大件数")
    parser.add_argument("--dry-run", action="store_true", help="APIを呼ばずに取得結果だけ表示")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=MAX_AGE_HOURS)

    # 1. RSS取得
    fetched, failed = [], 0
    for section, queries in QUERIES.items():
        for q in queries:
            try:
                got = fetch_feed(section, q)
                print(f"[{section}] {q}: {len(got)} 件")
                fetched.extend(got)
            except Exception as e:
                failed += 1
                print(f"[失敗] {q}: {e}", file=sys.stderr)
            time.sleep(REQUEST_INTERVAL)

    # 2. 期間で絞り、キャッシュ済み・重複を除く
    cache = load_cache()
    cached_ids = {a["id"] for a in cache["articles"]}
    recent = [a for a in fetched
              if datetime.fromisoformat(a["published"]) >= cutoff and a["id"] not in cached_ids]
    relevant = [a for a in recent if any(k in a["title"].lower() + " " for k in KEYWORDS)]
    unique = dedupe(relevant, [a["title"] for a in cache["articles"]])
    targets = pick(unique, args.limit)
    print(f"取得 {len(fetched)} 件 → 48時間以内・未翻訳 {len(recent)} 件 → 金属関連 {len(relevant)} 件"
          f" → 重複除去後 {len(unique)} 件 → 翻訳対象 {len(targets)} 件")

    if args.dry_run:
        for a in targets:
            print(f"  [{a['section']}] {a['published'][:16]} {a['source']}: {a['title']}")
        return
    if not targets:
        print("新しい記事はありません")
        return
    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[失敗] APIキーが未設定です（環境変数 ANTHROPIC_API_KEY または .env）", file=sys.stderr)
        sys.exit(1)

    # 3. 翻訳してキャッシュに追加
    try:
        results = translate(targets)
    except anthropic.AuthenticationError:
        print("[失敗] APIキーが無効か未設定です（環境変数 ANTHROPIC_API_KEY）", file=sys.stderr)
        sys.exit(1)
    except (anthropic.APIError, RuntimeError, ValueError) as e:
        print(f"[失敗] 翻訳: {e}", file=sys.stderr)
        sys.exit(1)

    added = 0
    for a in targets:
        r = results.get(a["id"])
        if not r:
            print(f"[警告] 翻訳結果なし: {a['title']}", file=sys.stderr)
            continue
        a.update(title_ja=r["title_ja"], summary_ja=r["summary_ja"], category=r["category"],
                 importance=r["importance"], translated_at=now.isoformat())
        cache["articles"].append(a)
        added += 1

    # 古い記事を落とし、新しい順に保存
    keep_from = (now - timedelta(days=KEEP_DAYS)).isoformat()
    cache["articles"] = sorted([a for a in cache["articles"] if a["published"] >= keep_from],
                               key=lambda a: a["published"], reverse=True)
    cache["updated_at"] = now.isoformat()
    save_cache(cache)
    print(f"翻訳 {added} 件を追加（キャッシュ合計 {len(cache['articles'])} 件）")
    if failed:
        print(f"[警告] RSS取得失敗 {failed} クエリ", file=sys.stderr)


if __name__ == "__main__":
    main()
