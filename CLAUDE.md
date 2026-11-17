# LME Metals Monitor — 開発仕様書

LME（ロンドン金属取引所）の主要非鉄金属の価格と関連ニュース（英語→日本語）を毎日自動収集し、スマホでも見やすいWebアプリとして表示する。

## 1. 目的
- LME主要6金属の公式価格（米ドル／トン）を一覧とチャートで確認する
- 期間ごとの騰落率（1日・1週間・1カ月・1年・3年・5年）をひと目で把握する
- ニッケル（ステンレス原料）と銅・アルミ（非鉄全般）の英語ニュースを日本語で読む

## 2. 対象データ
| 金属 | 英語名 | 表示 |
|---|---|---|
| 銅 | Copper | 必須 |
| アルミニウム | Aluminium | 必須 |
| ニッケル | Nickel | 必須 |
| 亜鉛 | Zinc | 必須 |
| スズ | Tin | 必須 |
| 鉛 | Lead | 必須 |

- 価格：LME Official Cash Settlement（現物）と 3カ月物。単位は USD/t
- 在庫：LME在庫（tons）も取れれば保存する（任意）

## 3. データソース
### 価格：Westmetall（無料）
- 最新値：https://www.westmetall.com/en/markdaten.php
- 過去データ：同ページの各金属の「Table」リンク先に履歴表がある想定。**最初に実際のページを取得してリンク構造・表の形式を確認すること**（URLは推測で書かない）
- 取得マナー：User-Agentを明示し、リクエスト間隔は1秒以上あける。1日の取得回数は最小限にする
- 取れなかった場合の代替：初回は取れる範囲で保存し、以降は毎日追記して蓄積する

### ニュース：Google News RSS（無料）
- 検索クエリの例（英語記事に限定：`hl=en-US&gl=US&ceid=US:en`）
  - ステンレス・ニッケル：`LME nickel`, `nickel price stainless`
  - 非鉄全般：`LME copper`, `LME aluminium`, `copper price`, `aluminium price`
- 直近24〜48時間の記事に絞る。URLとタイトルの類似で重複を除く
- 1日の翻訳対象は最大 20 件（APIコスト管理）

### 翻訳・要約：Claude API
- モデル：`claude-haiku-5-5`（安価で十分）
- 出力：日本語タイトル、2〜3行の要約、カテゴリ（ニッケル／銅／アルミ／その他）、重要度（高・中・低）
- 翻訳済みの記事は `data/news.json` にキャッシュし、同じ記事を再翻訳しない
- APIキーは環境変数 `ANTHROPIC_API_KEY`（GitHub Secrets）から読む

## 4. 技術構成
- バックエンド：Python 3.11（`requests`, `beautifulsoup4`, `feedparser`, `anthropic`）
- データ保存：リポジトリ内のCSV/JSONファイル（DB不要）
- フロントエンド：静的HTML＋JavaScript（チャートは Chart.js をCDNで読み込む）。ビルドツールは使わない
- 自動実行：GitHub Actions
- 公開：GitHub Pages

## 5. ディレクトリ構成
```
lme-metals-monitor/
├── CLAUDE.md
├── requirements.txt
├── scripts/
│   ├── backfill_prices.py   # 初回のみ：過去5年分の価格を取得
│   ├── update_prices.py     # 毎日：最新価格を追記
│   ├── fetch_news.py        # 毎日：ニュース取得＋翻訳
│   └── build_site_data.py   # 表示用JSONを生成
├── data/
│   ├── prices.csv           # date,metal,cash,three_month
│   ├── stocks.csv           # date,metal,stock（任意）
│   └── news.json            # 翻訳済みニュースのキャッシュ
├── docs/                    # GitHub Pagesの公開フォルダ
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── data/site_data.json
└── .github/workflows/daily.yml
```

## 6. 画面仕様（1ページ、スマホ優先）
1. **ヘッダー**：タイトル、最終更新日時（日本時間）、データの基準日（LME営業日）
2. **価格一覧表**：6金属 × 列［現物価格、3カ月物、1日、1週、1カ月、1年、3年、5年の騰落率］
   - 騰落率は上昇を緑、下落を赤で表示
   - スマホでは横スクロールできるようにする
3. **チャート**：金属を選ぶタブ ＋ 期間切替ボタン（1W／1M／1Y／3Y／5Y）。現物価格の推移を折れ線で表示
4. **ニュース**：2つのセクション
   - 「ステンレス関連（ニッケル）」
   - 「非鉄全般（銅・アルミ）」
   - 各記事：日本語タイトル、要約、媒体名、日付、元記事リンク（英語）。重要度「高」は上に出す
5. **フッター**：出典（Westmetall / LME、Google News）と「価格は参考値」の注記

騰落率の計算ルール：基準日以前で最も近い営業日の現物価格と比べる。データが足りない期間は「—」と表示する。

## 7. 自動実行（GitHub Actions）
- スケジュール：平日 23:00 JST（`cron: '0 14 * * 1-5'` UTC）
  - LME公式価格の公表はロンドン時間12:30〜13:25のため、日本時間の夜に実行する
- 手順：update_prices → fetch_news → build_site_data → 変更があればコミットしてpush
- 手動実行（`workflow_dispatch`）もできるようにする
- 失敗したらログで原因がわかるようにする。価格が取れなくてもニュースの処理は続ける

## 8. 開発の進め方（フェーズごとに動作確認してから次へ進む）
- **フェーズ1**：Westmetallのページを調べて、最新価格と過去データを取得する。`data/prices.csv` を作り、件数・期間・欠損を報告する
- **フェーズ2**：`fetch_news.py` を作り、ニュース取得と翻訳を5件で試す
- **フェーズ3**：`build_site_data.py` と画面（docs/）を作り、ローカルで表示を確認する（`python -m http.server`）
- **フェーズ4**：GitHub Actions と GitHub Pages を設定する（手順を日本語で案内する）

## 9. ルール
- 説明やコメントは日本語で書く
- 外部サイトの構造は推測せず、実際に取得して確認してから実装する
- APIキーなどの秘密情報をコードやリポジトリに書かない
- コストを抑える：Claude APIの呼び出しは1日1回の実行で完結させ、翻訳済みの記事は再翻訳しない

## 10. 注意
- LMEの価格データには再配布のルールがある。このアプリは個人の情報収集用として使う
- GitHub Pagesは公開URLになる（無料プランでは非公開にできない）。気になる場合はCloudflare Pagesのアクセス制限などを検討する
