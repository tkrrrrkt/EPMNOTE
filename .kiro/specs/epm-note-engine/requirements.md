# Requirements Document

## Introduction

EPM Note Engine（Code Name: ValueCruise）は、経営管理SaaS「EPM」の認知獲得・リード創出を目的とした、Note記事の半自動生成システムである。

本システムは「Autonomous Marketing RAG with Last-Mile Automation」をコアアーキテクチャとし、以下の価値を提供する：
- SEO競合分析と自己推敲による高品質記事の生成
- ユーザーの暗黙知（失敗談・画像・音声）の構造化・資産化
- 記事作成からNote.comへの下書き保存までの自動化

**対象ユーザー**: Product Owner（Tomoyuki氏）
**運用目標**: 週2本のNote記事投稿

---

## Requirements

### Requirement 1: 記事候補管理・選択

**Objective:** As a マーケティング担当者, I want 記事候補を一覧から選択してSEOキーワードを設定できる, so that 効率的に記事作成を開始できる

#### Acceptance Criteria

1. When ユーザーがアプリケーションを起動した時, the EPM Note Engine shall サイドバーに記事候補一覧を表示する
2. When ユーザーが記事候補を選択した時, the EPM Note Engine shall 選択した記事の詳細情報（タイトル、ターゲットペルソナ）を表示する
3. When ユーザーがSEOキーワードを入力して確定した時, the EPM Note Engine shall 記事のステータスを `PLANNING` から `RESEARCHING` に更新する
4. The EPM Note Engine shall 記事のステータス（PLANNING, RESEARCHING, WAITING_INPUT, DRAFTING, REVIEW, COMPLETED）を視覚的に識別可能な形式で表示する
5. While 記事が選択されている間, the EPM Note Engine shall 現在の進捗フェーズをUIに表示する

---

### Requirement 2: SEOリサーチ・競合分析

**Objective:** As a マーケティング担当者, I want AIが競合記事を分析して構成案を提案してくれる, so that SEOで上位表示を狙える記事構成を作成できる

#### Acceptance Criteria

1. When SEOキーワードが確定した時, the Research Agent shall Tavily APIを使用して競合上位記事を検索・分析する
2. When 競合分析が完了した時, the Research Agent shall 競合記事のURL、見出し構成、Content Gapを抽出してDBに保存する
3. When 競合分析が完了した時, the Research Agent shall ChromaDBから関連する社内資料を検索する
4. When リサーチが完了した時, the EPM Note Engine shall 「競合に勝つ構成案」と「情報のGap」をUIに表示する
5. The EPM Note Engine shall リサーチ結果の要約をresearch_summaryカラムに保存する
6. If Tavily APIへの接続が失敗した場合, the EPM Note Engine shall エラーメッセージを表示し、リトライオプションを提供する

---

### Requirement 3: エッセンス注入（テキスト入力）

**Objective:** As a マーケティング担当者, I want 自分の知見や素材（テキスト）を記事に注入できる, so that オリジナリティのある差別化された記事を作成できる

#### Acceptance Criteria

1. When リサーチフェーズが完了した時, the EPM Note Engine shall エッセンス入力フォームを表示する
2. When ユーザーがテキストでエッセンス（失敗談、意見、技術知見、フック）を入力した時, the EPM Note Engine shall snippetsテーブルに保存する
3. ~~When ユーザーが画像ファイルをドラッグ＆ドロップした時, the EPM Note Engine shall ファイルをuploadsフォルダに保存し、snippetsに関連付ける~~ **[MVP対象外]**
4. ~~When ユーザーが音声ファイルをドラッグ＆ドロップした時, the EPM Note Engine shall ファイルをuploadsフォルダに保存し、snippetsに関連付ける~~ **[MVP対象外]**
5. The EPM Note Engine shall スニペットにカテゴリ（FAILURE, OPINION, TECH, HOOK）を設定可能とする
6. When エッセンス入力が完了した時, the EPM Note Engine shall 記事のステータスを `WAITING_INPUT` から `DRAFTING` に更新する

---

### Requirement 4: 記事生成・品質レビューループ

**Objective:** As a マーケティング担当者, I want AIが自動で記事を生成し、品質チェックして改善してくれる, so that 一定品質以上の記事を効率的に作成できる

#### Acceptance Criteria

1. When ドラフティングフェーズが開始した時, the Drafting Agent shall リサーチ結果とエッセンスを基に記事本文（Markdown形式）を生成する
2. When 記事本文が生成された時, the Drafting Agent shall 図解生成用のプロンプト（image_prompts）を生成する
3. When 記事本文が生成された時, the Drafting Agent shall SNS投稿文案（X, LinkedIn用）を生成する
4. When 記事本文が生成された時, the Drafting Agent shall タイトル候補を複数（title_candidates）生成する
5. When ドラフトが完成した時, the Reviewer Agent shall 記事の品質を評価する（ターゲットへの訴求力、論理構成、SEO適合性）
6. If レビュースコアが80点未満の場合, the EPM Note Engine shall 修正指示を付けてDrafting Agentに差し戻す（最大1回）
7. When レビュースコアが80点以上の場合, the EPM Note Engine shall 記事のステータスを `REVIEW` から `COMPLETED` に近い状態に更新し、エディタ画面に遷移する
8. The EPM Note Engine shall ドラフト生成中は処理状況をUIに表示する

---

### Requirement 5: 記事エディタ・最終編集

**Objective:** As a マーケティング担当者, I want 生成された記事を確認・編集できる, so that 最終的な品質を自分でコントロールできる

#### Acceptance Criteria

1. When レビューフェーズが完了した時, the EPM Note Engine shall 記事エディタ画面を表示する
2. The EPM Note Engine shall 記事本文をMarkdownエディタで編集可能とする
3. The EPM Note Engine shall タイトル候補から最終タイトルを選択可能とする
4. The EPM Note Engine shall SNS投稿文案を確認・編集可能とする
5. When ユーザーが記事を保存した時, the EPM Note Engine shall final_content_mdを更新する
6. The EPM Note Engine shall 画像プロンプト（図解生成指示）を表示する

---

### Requirement 6: Note.com自動投稿

**Objective:** As a マーケティング担当者, I want ボタン1つでNote.comに下書き保存できる, so that 投稿作業の手間を最小化できる

> **MVP Note**: 画像アップロードはMVP対象外。テキスト（タイトル・本文）のみ下書き保存する。

#### Acceptance Criteria

1. When 記事が完成状態の時, the EPM Note Engine shall 「Noteへ下書き保存」ボタンを表示する
2. When ユーザーが「Noteへ下書き保存」ボタンをクリックした時, the Playwright Automation shall ヘッドレスブラウザを起動する
3. When ブラウザが起動した時, the Playwright Automation shall 環境変数のNOTE_EMAIL/NOTE_PASSWORDを使用してNote.comにログインする
4. When ログインが成功した時, the Playwright Automation shall 新規投稿画面を開き、タイトルと本文を入力する（画像アップロードはMVP対象外）
5. When 本文入力が完了した時, the Playwright Automation shall 「下書き保存」を実行する
6. When 下書き保存が成功した時, the EPM Note Engine shall is_uploadedフラグをTrueに更新し、成功メッセージを表示する
7. If Note.comへのログインが失敗した場合, the EPM Note Engine shall エラーメッセージを表示し、認証情報の確認を促す
8. If 下書き保存が失敗した場合, the EPM Note Engine shall エラー内容を表示し、リトライオプションを提供する
9. While Playwright処理が実行中の間, the EPM Note Engine shall 処理状況をUIに表示する

---

### Requirement 7: ナレッジ資産管理

**Objective:** As a マーケティング担当者, I want 過去に入力したエッセンスや記事を再利用できる, so that 知識を蓄積・活用できる

#### Acceptance Criteria

1. The EPM Note Engine shall 過去のスニペット（エッセンス）をChromaDBにインデックス化する
2. When 新規記事のリサーチ時, the Research Agent shall 過去記事とスニペットから関連情報を検索可能とする
3. The EPM Note Engine shall スニペットにタグを設定可能とする
4. The EPM Note Engine shall 公開済み記事のURL（published_url）と成果指標（metrics: PV, likes, CTR）を記録可能とする

---

### Requirement 8: データ永続化・状態管理

**Objective:** As a システム管理者, I want データが確実に永続化される, so that 作業の中断・再開が可能になる

#### Acceptance Criteria

1. The EPM Note Engine shall 記事データをPostgreSQLに永続化する
2. The EPM Note Engine shall ベクトルデータをChromaDBに永続化する（Persistent Client）
3. The EPM Note Engine shall アップロードファイルをdata/inputs/uploads/に保存する
4. When ユーザーがアプリケーションを再起動した時, the EPM Note Engine shall 前回の作業状態を復元する
5. The EPM Note Engine shall 各記事の作成日時（created_at）と更新日時（updated_at）を記録する

---

## Non-Functional Requirements

### NFR-1: パフォーマンス
- The EPM Note Engine shall AIによる記事生成を5分以内に完了する
- The EPM Note Engine shall UI操作に対して2秒以内に応答する

### NFR-2: セキュリティ
- The EPM Note Engine shall APIキー・認証情報を環境変数で管理し、コードにハードコードしない
- The EPM Note Engine shall Note.comの認証情報を安全に保管する

### NFR-3: 可用性
- The EPM Note Engine shall ローカル環境（Docker Compose）で動作する
- The EPM Note Engine shall PostgreSQL/ChromaDBの起動状態を確認し、未起動時はエラーを表示する
