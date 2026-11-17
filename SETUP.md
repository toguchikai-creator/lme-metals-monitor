# 公開・自動実行のセットアップ手順（フェーズ4）

GitHub にリポジトリを作り、毎日の自動更新（GitHub Actions）と公開（GitHub Pages）を設定します。
所要時間は 15〜20 分ほどです。

---

## 0. 事前に知っておくこと

- **GitHub Pages は無料プランだと公開リポジトリ（Public）が必要**です。公開URLは誰でも見られます。
  - 価格データ（CSV）とニュースの翻訳もリポジトリ上で誰でも見られる状態になります。
  - LME の価格データには再配布のルールがあるため、URL は人に広めず個人利用にとどめてください。
  - 非公開にしたい場合は、GitHub Pro（有料）で Private リポジトリ＋Pages、または Cloudflare Pages のアクセス制限を検討します。
- **APIキーはリポジトリに入りません**。`.env` は `.gitignore` で除外済みです。GitHub には「Secrets」として別に登録します。

---

## 1. GitHub でリポジトリを作る

1. https://github.com にログインします（アカウントがなければ作成）。
2. 右上の「＋」→「New repository」を開きます。
3. 次のように入力します。
   - Repository name：`lme-metals-monitor`
   - Public を選択
   - 「Add a README file」などのチェックは**すべて外したまま**にする
4. 「Create repository」を押します。

## 2. 手元のファイルを GitHub に送る（push）

Claude にお願いする場合は、**GitHub のユーザー名**を伝えてください。コミットまで代わりに行います。
自分で行う場合は、プロジェクトのフォルダで次を順に実行します（`<ユーザー名>` は置き換え）。

```bash
git config user.name "<ユーザー名>"
git config user.email "<ユーザー名>@users.noreply.github.com"
git commit -m "初回コミット"
git remote add origin https://github.com/<ユーザー名>/lme-metals-monitor.git
git push -u origin main
```

- メールアドレスは GitHub の「noreply」アドレスにしておくと、本当のメールアドレスが公開されません。
- push のときにログインを求められたら、画面の案内に従ってブラウザで認証します。

## 3. APIキーを Secrets に登録する

1. GitHub のリポジトリ画面で「Settings」→ 左メニュー「Secrets and variables」→「Actions」を開きます。
2. 「New repository secret」を押します。
3. 次のように入力して「Add secret」を押します。
   - Name：`ANTHROPIC_API_KEY`
   - Secret：Claude APIキー（`sk-ant-` で始まる文字列）

## 4. GitHub Pages を有効にする

1. 「Settings」→ 左メニュー「Pages」を開きます。
2. 「Build and deployment」の「Source」で **「GitHub Actions」** を選びます。
   （「Deploy from a branch」ではありません）

## 5. 最初の1回を手動で実行する

1. リポジトリ画面の上部「Actions」タブを開きます。
2. 左の一覧から「daily-update」を選び、右の「Run workflow」→「Run workflow」を押します。
3. 数分待つと、緑のチェックが付きます。
   - `update`（価格・ニュース更新）と `deploy`（公開）の2つが順に動きます。
4. `deploy` の中に表示される URL が公開ページです。
   通常は `https://<ユーザー名>.github.io/lme-metals-monitor/` です。

以後は、**平日 23:00（日本時間）に自動で実行**されます。

---

## うまくいかないとき

| 症状 | 確認すること |
|---|---|
| 赤い×が付いた | 「Actions」→ 失敗した実行 → 赤い×のステップを開くと、日本語で原因が出ています |
| 「ニュースの取得・翻訳に失敗」 | Secrets の名前が `ANTHROPIC_API_KEY` になっているか。Anthropic Console にクレジットが残っているか |
| 「価格の更新に失敗」 | Westmetall のサイトが一時的に落ちているか、ページの作りが変わった可能性。数日続くなら Claude に相談 |
| `deploy` で失敗する | 手順4の Source が「GitHub Actions」になっているか |
| push で `permission denied` | 「Settings」→「Actions」→「General」→「Workflow permissions」を「Read and write permissions」にする |

### 補足
- 価格かニュースのどちらかが失敗しても、残りの処理と公開は続きます（最後に失敗として記録されます）。
- GitHub の定期実行は、混雑していると数十分遅れることがあります。
- リポジトリに 60 日間まったく動きがないと、定期実行が自動で止まることがあります。毎日のデータ更新コミットがあれば通常は止まりません。止まった場合は「Actions」画面から有効にし直します。
- 画面（`docs/` のファイル）を直して push したときは、データ更新をせずに公開だけやり直します。
