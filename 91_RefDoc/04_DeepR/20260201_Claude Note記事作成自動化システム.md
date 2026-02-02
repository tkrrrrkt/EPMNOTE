# Note記事自動化の最前線：日本エンジニアによる技術的実装事例

**公式APIが存在しないNoteプラットフォームに対し、日本のエンジニアたちはSelenium/Playwright＋非公式API解析のハイブリッド手法を確立している。** 2024〜2025年にかけて、Claude/GPT-4oとの組み合わせによるAI記事生成から投稿までの完全自動化事例が急増。品質担保では「生成と評価の分離」「LLMによる自己レビュー」「Human-in-the-Loop設計」の3パターンが定番化しつつある。本調査では、Qiita・Zenn・Note技術カテゴリから抽出した先進的実装事例を技術的詳細とともに解説する。

---

## 先進的な実装事例ベスト5

### 事例1: GitHub Actions + Claude + Playwrightによる完全自動化パイプライン

**出典**: note.com/joyous_hawk969/n/n7e325e86a3db（gonuts🍩、2025年10月）

|項目|詳細|
|---|---|
|**技術スタック**|GitHub Actions + Claude Code SDK + Claude Sonnet 4.5 + Tavily API + Playwright|
|**自動化範囲**|テーマ入力 → リサーチ → 執筆 → ファクトチェック → Note下書き保存まで|
|**トリガー**|GitHub上での手動実行（スマホ/PCから）|

この事例の特筆すべき点は**ファクトチェック工程の組み込み**だ。Tavily APIを使ったWeb検索によるファクトチェックをパイプラインに含め、ハルシネーションリスクを低減している。Human-in-the-Loopとして、自動生成後は下書き保存し人間確認後に公開する設計を採用。

---

### 事例2: Playwright + Google Vertex AI Imagen によるAI画像生成付き自動投稿

**出典**: note.com/bestinksalesman/n/n5a76c328c301（広東語スラング先生、2025年10月）

|項目|詳細|
|---|---|
|**技術スタック**|Node.js + Playwright + Google Vertex AI Imagen + Gemini API + Sharp|
|**自動化範囲**|Markdown読込 → AI画像生成 → 認証 → タイトル/本文入力 → 下書き/公開|
|**処理時間**|初回約33秒、2回目以降約18秒（認証状態永続化）|

**画像生成の自動化**が最大の特徴。記事のキーワードから自動でテーマを判定し、Vertex AI Imagenでサムネイル画像を生成。画像はBase64変換→クリップボード経由でペーストする手法で、Noteの独自エディタに対応している。

---

### 事例3: Claude Code Skill/Subagentによる文体再現システム

**出典**: qiita.com/cardene/items/5b488d7671476b6acf77（かるでね@cardene777、2025年11月）

|項目|詳細|
|---|---|
|**技術スタック**|Claude Code（Skill + Subagent）+ MCP（Context7, Kiri, GitHub）+ WebFetch/WebSearch|
|**自動化範囲**|過去記事分析 → スタイル抽出 → 新規記事執筆 → プラットフォーム最適化|
|**RAG実装**|過去記事から6要素（テーマ、課題、解決策、コード例、前提知識、制約）を抽出|

```
.claude/
├── agents/
│   ├── article-analyzer.md    # 記事分析Subagent
│   └── article-writer.md      # 記事執筆Subagent
└── skills/
    ├── analysis_framework/    # 記事分析フレームワーク
    ├── article_templates/     # 記事テンプレート集
    └── tone_guidelines/       # 文体・スタイルガイドライン
```

**過去記事からの文体学習**が特徴的。`wordings.md`に頻出表現をカテゴリ別に整理し、言い回しパターンを再現。Qiita/Zenn/Zenn Bookの記法差異もテンプレートで吸収している。

---

### 事例4: DifyワークフローによるSEO記事作成（10ステップ構成）

**出典**: note.com/kakeyang/n/n0f1359efbeb1（掛谷知秀、2024年6月）

|項目|詳細|
|---|---|
|**技術スタック**|Dify v0.6.9+ + GPT-4o + Web Scraper + Jinja2テンプレート|
|**自動化範囲**|参照URL取得 → スクレイピング → 見出し構成 → レビュー → 本文生成|
|**品質担保**|LLMによる自己レビュー工程を設計|

10ステップの処理フローで、**見出し構成の自己レビュー工程**が品質向上のキーポイント。GPT-4oに構成案を生成させた後、同じGPT-4oに再度レビュー・修正させることで精度を向上させている。Iterationノードによるループ処理で、複数URLの並列スクレイピングも実現。

---

### 事例5: Python NoteClientライブラリ（PyPI公開）

**出典**: github.com/Mr-SuperInsane/NoteClient + nao-kun.com（なおくん、2026年1月更新）

|項目|詳細|
|---|---|
|**技術スタック**|Python 3.x + Selenium（v1）/ 内部API直接利用（v2）|
|**自動化範囲**|ログイン → 記事作成 → タグ設定 → 公開/下書き選択|
|**インストール**|`pip install NoteClient`|

```python
from Note_Client import Note
note = Note(email=EMAIL, password=PASSWORD, user_id=USER_ID)
note.create_article(
    title=TITLE, 
    file_name='content.txt', 
    input_tag_list=['sample_tag'],
    post_setting=True  # True=公開, False=下書き
)
```

2026年1月リリースの**Note Client 2**では、Selenium依存を脱却し内部API直接利用による高速化を実現。有料記事投稿や画像アップロードにも対応している。

---

## 品質担保のためのアーキテクチャ・工夫

### プロンプトチェーン：生成と評価の分離

Algomatic Tech Blogの実装事例では、「回答生成」と「回答評価」を別々のプロンプトに分離する設計を推奨している。単一プロンプトで全てを処理するのではなく、生成→評価→修正のチェーンを組むことで精度が向上する。

```json
{
  "reason": "分類結果の理由",
  "category": "問い合わせの種類 または 判断保留",
  "uncertaintyPoints": ["判断に迷った点1", "判断に迷った点2"],
  "requiresHumanReview": true,
  "humanReviewReason": "人間によるレビューが必要な理由"
}
```

**「判断保留」という逃げ道を作る設計**が重要。確信が持てないケースは`requiresHumanReview: true`フラグで人間判断を要求し、無理な出力を避ける。

---

### ReActパターンによる推論可視化

Reason（思考）→ Act（行動）→ Observation（観察）の3ステップループ構造により、**推論過程を可視化**できる。デバッグや品質向上に有効で、ツール連携（検索API、計算機能等）との統合も自然に行える。

```python
def reason_and_act(llm_call, user_input: str, tools: dict) -> str:
    reasoning_log = ""
    observations_log = []
    while True:
        # Reason: 過去の推論と観察情報を踏まえて次の行動を判断
        # Act: ツール呼び出しまたは最終回答
        # Observation: 行動結果をログに蓄積
```

---

### マルチエージェントによるクロスチェック

AutoGenを使った記事自動生成では、**4つの専門エージェント**による役割分担を実装：

- **ResearcherAgent**: Qiita/Zennを検索して情報整理
- **ArchitectAgent**: 記事構成案（アウトライン）作成
- **WriterAgent**: 記事本文執筆
- **ReviewerAgent**: 品質レビュー・フィードバック

ReviewerAgentとWriterAgentの対話的やりとりにより、単一LLMでは得られない品質向上を実現している。

---

### Human-in-the-Loop設計の実践パターン

Clineを使った技術ブログ執筆では、以下の役割分担マトリクスを採用：

|作業フェーズ|AI担当|人間担当|
|---|---|---|
|記事構成初期案|✓|レビュー|
|詳細な技術解説|ドラフト|検証・補足|
|コード例の作成|ベース|テスト・修正|
|最終校正|文法チェック|内容確認|

この分担により、**執筆時間を6〜8時間から2〜3時間に短縮**しつつ品質を維持している。

---

## Note連携の技術的ハック

### 非公式APIエンドポイント一覧

Noteは公式APIを公開していないが、エンジニアによる解析で以下のエンドポイントが判明している：

|エンドポイント|用途|
|---|---|
|`POST /api/v1/text_notes`|記事作成|
|`PUT /api/v1/text_notes/{id}`|記事更新|
|`POST /api/v1/upload_image`|画像アップロード|
|`POST /api/v3/drafts`|下書き保存|
|`POST /api/v2/notes/{note_key}/publish`|公開|
|`GET /api/v2/creators/{username}/contents`|記事一覧取得|

---

### 認証突破の3パターン

**パターン1: Selenium→Cookie取得ハイブリッド方式（推奨）**

```python
from selenium import webdriver
from selenium.webdriver.common.by import By

def get_note_cookies(email, password):
    driver = webdriver.Chrome()
    driver.get('https://note.com/login')
    # ログイン操作...
    cookies = driver.get_cookies()
    cookie_dict = {cookie['name']: cookie['value'] for cookie in cookies}
    return cookie_dict
```

Seleniumでログイン→Cookie取得→以降はrequestsで高速API呼び出し、というハイブリッド方式が最もバランスが良い。

**パターン2: Playwright storageState方式**

```javascript
const context = await browser.newContext({ 
    storageState: '/path/to/auth/note.json',
    locale: 'ja-JP' 
});
```

初回ログイン時にセッション情報をJSONとして保存し、2回目以降は再利用。処理時間を**33秒→18秒に短縮**できる。

**パターン3: ブックマークレット方式**

手動でログイン後、ブックマークレットをクリックしてCookie/認証トークンを取得する斬新な方式。直接ログイン処理を再現するのではなく、**ブラウザのセッション情報を横取り**する発想。

---

### Noteエディタ操作の注意点

Noteは独自のリッチテキストエディタを採用しており、以下の対応が必要：

- **Markdown直接入力不可**: Seleniumで自然な入力処理を実装する必要あり
- **画像挿入**: Base64変換→クリップボード→ペーストが確実
- **サムネイル設定**: トリミングダイアログ等の複雑なUI操作が必要

---

## 関連技術トレンド

### LangChain/LangGraphの日本実装

LangChainのAgentsパターンを使った記事生成が主流。Google Search APIと連携し、リアルタイム情報を取得して記事化するワークフローが多い。

**LangGraphの特徴的な違い**として、LangChainが一方向処理（A→B→C）なのに対し、LangGraphは**循環的な処理フロー**が可能。条件分岐・ループ処理を組み込んだ複雑なワークフローに適している。

```python
from langgraph.graph import StateGraph, START, END
graph_builder.add_conditional_edges("node_1", decide_mood)  # 条件分岐
```

---

### Difyによるノーコードワークフロー

Difyは**ノーコードでAIワークフローを構築**できるプラットフォームとして急速に普及。以下の特徴がある：

- Iterationノードによるループ処理（複数URL並列スクレイピング等）
- Web Scraperによる外部サイト取得
- Jinja2テンプレートによる出力整形
- API自動生成による外部システム連携

ただし、Iterationでのネスト（多重ループ）不可、JSON直接入力不可などの制約も存在する。

---

### Make/GAS/n8nの使い分け

|ツール|強み|推奨用途|
|---|---|---|
|**GAS**|無料、Googleサービス連携、定期実行|シンプルな定期処理、Slack/Gmail連携|
|**Make**|ビジュアル設計、豊富なコネクタ|SNS連携、複数サービス組合せ|
|**n8n**|無料セルフホスト、高度なカスタマイズ|社内システム連携、複雑なワークフロー|

n8n + Gemini APIの組み合わせで、**リリースノート自動収集→要約→通知**のワークフローを構築した事例（クラウドエース）も登場している。

---

## 実装時の注意点と推奨事項

**技術的リスク**: Noteの非公式APIは予告なく仕様変更される可能性がある。レート制限（目安：1分間に10リクエスト程度）にも注意が必要。

**運用上の推奨事項**として、完全自動公開ではなく**下書き保存→人間確認→公開**のHuman-in-the-Loopフローを採用すべき。Note利用規約との整合性も確認が必要だ。

**推奨技術スタック**は「Playwright + Cookie永続化 + 非公式API」のハイブリッド方式。複雑なUI操作を回避しつつ、高速な投稿処理を実現できる。AI部分はClaude/GPT-4oとLangChain/Difyの組み合わせが現時点で最も実績が多い。

---

## Conclusion

日本のエンジニアコミュニティでは、Noteの公式API不在という制約を乗り越え、**Playwright/Seleniumによるブラウザ自動化と非公式API解析のハイブリッド手法**が確立されている。品質担保では「生成と評価の分離」「マルチエージェントによるクロスチェック」「Human-in-the-Loop設計」の3パターンが定番化。特にClaude Code Skill/Subagentを使った文体再現システムや、Difyによるノーコードワークフローなど、2024〜2025年にかけて技術的成熟度が大きく向上した。今後はLangGraphの循環フロー機能を活用した、より高度な自己改善型記事生成システムへの発展が期待される。