# Implementation Plan

## Overview

EPM Note Engine（ValueCruise）の実装タスク。Layered Architecture（UI → Logic → Data）に従い、データ層から順に構築する。

**アーキテクチャ原則**:
- 依存方向: Data Layer → Logic Layer → UI Layer
- 設定一元化: config.py で外部API・環境変数を集約管理
- 状態同期: LangGraph ArticleState と Streamlit session_state の明確な境界

---

## Tasks

- [ ] 1. プロジェクトセットアップ・インフラ構築
- [ ] 1.1 開発環境とDocker Compose構成の作成
  - Python 3.10+環境、依存パッケージ管理（pyproject.toml + requirements.txt）
  - Docker Composeで PostgreSQL 15+ を起動
  - 環境変数テンプレート（.env.example）の作成
  - .gitignoreの設定（.env, data/, uploads/, __pycache__/）
  - ディレクトリ構造の作成（src/, tests/, data/chroma_db/, data/uploads/）
  - _Requirements: 8.1, 8.2, 8.3, NFR-3_

- [ ] 1.2 外部API設定基盤の構築
  - config.py: 環境変数からのAPIキー読み込みユーティリティ
  - Pydantic Settings による型安全な設定管理
  - APIクライアント初期化パターンの統一（Anthropic, OpenAI, Tavily）
  - 認証情報のバリデーション（起動時チェック）
  - _Requirements: NFR-2_

- [ ] 2. データモデル・永続化層
- [ ] 2.1 PostgreSQLモデルとマイグレーション
  - SQLAlchemy 2.0 を使用した Article / Snippet モデルの定義
  - UUID主キー、JSONB型カラム（competitor_analysis, title_candidates, sns_posts等）
  - ステータスENUM（PLANNING, RESEARCHING, WAITING_INPUT, DRAFTING, REVIEW, COMPLETED）
  - タイムスタンプ（created_at, updated_at）の自動更新
  - 初期マイグレーションスクリプトの作成（Alembic推奨）
  - _Requirements: 8.1, 8.4, 8.5_

- [ ] 2.2 (P) ArticleRepository の実装
  - 全記事一覧取得、ID検索、作成、更新のCRUD操作
  - ステータス遷移の更新ロジック（状態遷移バリデーション含む）
  - ステータス別フィルタリング（サイドバー表示用）
  - _Requirements: 1.1, 1.2, 8.1_

- [ ] 2.3 (P) SnippetRepository の実装
  - スニペット（エッセンス）のCRUD操作
  - カテゴリ（FAILURE, OPINION, TECH, HOOK）とタグの管理
  - 記事IDによる関連スニペット取得
  - _Requirements: 3.2, 3.5, 7.3_

- [ ] 2.4 (P) ChromaDB RAGService の実装
  - Persistent Clientでの初期化（パス: `data/chroma_db/`）
  - knowledge_base / archive_index コレクションの作成
  - ドキュメント追加（メタデータ: source_path, document_type, article_id）
  - 類似検索インターフェース（top_k, フィルタリング対応）
  - _Requirements: 7.1, 7.2, 8.2_

- [ ] 2.5 記事候補マスターデータのシード投入
  - `91_RefDoc/02_生成AIとのやりとり履歴/05_記事候補.md` のパース
  - 60記事候補の抽出（Season 1-5, Week 1-30）
  - DBスキーマへのマッピング:
    - week_id: "Week1-1", "Week1-2" 形式
    - title: 記事タイトル
    - target_persona: コンテンツマップから推定
    - hook_statement: 会議の一言
    - content_outline: 見出し案
    - status: PLANNING（初期値）
  - シードスクリプト（seed_articles.py）の作成
  - _Requirements: 1.1_

- [ ] 3. UI Layer基盤（Streamlit）
- [ ] 3.1 Streamlitアプリケーション骨格の作成
  - app.pyエントリポイント
  - セッション状態管理設計:
    - `st.session_state.current_article_id`: 選択中の記事ID
    - `st.session_state.workflow_state`: LangGraph ArticleState のミラー
    - `st.session_state.ui_phase`: UI表示用フェーズ（sidebar/input/editor）
  - サイドバー・メインエリアのレイアウト構成
  - 進捗フェーズの視覚的表示コンポーネント（st.progress, カラーインジケータ）
  - LangGraph状態とsession_stateの同期ユーティリティ
  - _Requirements: 1.4, 1.5, 4.8_

- [ ] 3.2 Sidebar - 記事選択コンポーネント
  - 記事候補一覧の表示（ArticleRepositoryから取得）
  - ステータス別カラーバッジ表示
  - 選択時に詳細情報（タイトル、ペルソナ、フック）を表示
  - SEOキーワード入力フィールドとステータス更新（PLANNING → RESEARCHING）
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [ ] 3.3 InputForm - エッセンス入力コンポーネント
  - テキスト入力フォーム（失敗談、意見、技術知見、フック）
  - カテゴリ選択ドロップダウン
  - スニペット保存とステータス遷移（WAITING_INPUT → DRAFTING）
  - 既存スニペットの一覧表示と編集
  - _Requirements: 3.1, 3.2, 3.5, 3.6_

- [ ] 3.4 Editor - 記事編集コンポーネント
  - Markdownエディタによる本文編集（st.text_area or streamlit-ace）
  - タイトル候補からの選択UI（st.radio）
  - SNS投稿文案の確認・編集（X, LinkedIn別タブ）
  - 画像プロンプト（image_prompts）の表示（コピーボタン付き）
  - final_content_md の保存
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [ ] 4. Logic Layer - Research Agent
- [ ] 4.1 Tavily API クライアントの実装
  - config.py の設定を使用したクライアント初期化
  - 競合上位記事の検索（search depth: advanced）
  - URL、見出し構成、スニペットの抽出
  - 接続失敗時のエラーハンドリングとリトライ（max 3回、exponential backoff）
  - _Requirements: 2.1, 2.6_

- [ ] 4.2 ResearchAgent の実装
  - Tavilyによる競合分析（上位5-10記事）
  - ChromaDBからの社内資料検索（関連ドキュメント取得）
  - Content Gap の抽出と構成案の生成（GPT-4o使用）
  - research_summary の生成とDB保存
  - CompetitorAnalysis / ResearchResult データクラスの実装
  - _Requirements: 2.2, 2.3, 2.4, 2.5_

- [ ] 5. Logic Layer - Writer / Reviewer Agents
- [ ] 5.1 WriterAgent の実装
  - Claude 3.5 Sonnet API による記事本文生成（Markdown形式、3000-4000字目標）
  - タイトル候補（title_candidates）の複数生成（3-5案）
  - 図解プロンプト（image_prompts）の生成
  - SNS投稿文案（X: 140字、LinkedIn: 300字）の生成
  - DraftResult データクラスの実装
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ] 5.2 ReviewerAgent の実装
  - スコアリングルーブリック（訴求力30/論理40/SEO30）に基づく評価
  - Claude 3.5 Sonnet による構造化出力（ScoreBreakdown）
  - 80点未満時の具体的修正フィードバック生成
  - 合否判定（passed: bool）の出力
  - ReviewResult データクラスの実装
  - _Requirements: 4.5, 4.6, 4.7_

- [ ] 6. LangGraphワークフロー統合
- [ ] 6.1 ArticleState TypedDictとグラフ構造の定義
  - langgraph==0.2.* をバージョン固定（requirements.txtに明記）
  - 状態フィールド（phase, seo_keywords, draft_content, review_score, retry_count等）
  - ノード定義（research, waiting_input, drafting, review, complete）
  - 条件分岐エッジ:
    - review score < 80 かつ retry_count < 1 → drafting へ戻る
    - review score >= 80 または retry_count >= 1 → complete へ
  - グラフのコンパイルとチェックポイント設定
  - _Requirements: 4.5, 4.6, 4.7_

- [ ] 6.2 ワークフロー実行サービスの実装
  - WorkflowService クラス: run_workflow / resume_workflow
  - 処理状況のUI通知（st.status / st.spinner との連携）
  - 最大リトライ回数（1回）の制御
  - 中断・再開のためのチェックポイント永続化
  - _Requirements: 4.6, 4.8_

- [ ] 6.3 UI-Logic統合
  - Sidebar → Research → InputForm → Drafting → Review → Editor の一連フロー接続
  - session_state と ArticleState の双方向同期
  - フェーズ遷移時のUI自動更新
  - _Requirements: 1.3, 3.6, 4.7_

- [ ] 7. PlaywrightによるNote.com自動化
- [ ] 7.1 NoteUploader の実装
  - Headless Browserの起動と設定（Chromium）
  - config.py からのNOTE_EMAIL/NOTE_PASSWORD取得
  - Note.comへのログイン自動化
  - セッション管理（Cookieの永続化検討）
  - _Requirements: 6.2, 6.3, NFR-2_

- [ ] 7.2 下書き保存フローの実装
  - 新規投稿画面への遷移（URL: note.com/new）
  - タイトル入力（セレクタ: data-testid推奨、フォールバック用CSS準備）
  - 本文（Markdown）の入力
  - 下書き保存ボタンのクリックと完了確認
  - is_uploadedフラグの更新
  - _Requirements: 6.1, 6.4, 6.5, 6.6_

- [ ] 7.3 エラーハンドリングとリトライ
  - ログイン失敗時のエラーメッセージ表示（認証情報確認を促す）
  - 保存失敗時のスクリーンショット保存（data/screenshots/）
  - リトライオプションの提供（UIボタン）
  - 処理中のUI進捗表示（st.spinner）
  - _Requirements: 6.7, 6.8, 6.9_

- [ ] 8. テスト・品質検証
- [ ] 8.1 ユニットテストの作成
  - ResearchAgent: 競合分析ロジック（Tavily APIモック）
  - WriterAgent: 記事生成ロジック（Claude APIモック）
  - ReviewerAgent: スコアリングロジック（境界値テスト含む）
  - RAGService: ベクトル検索（インメモリChromaDB）
  - Repository層: CRUD操作（テスト用SQLite or PostgreSQL）
  - pytest + pytest-asyncio 使用
  - _Requirements: NFR-1_

- [ ] 8.2 ワークフローE2Eテスト（モック環境）
  - LangGraphワークフロー全体の結合テスト
  - 外部API（Tavily, Claude）はモックで代替
  - レビューループ（80点未満 → 修正）の動作確認
  - 状態復元のテスト（チェックポイントからの再開）
  - Playwright部分はモック（実際のNote.comアクセスなし）
  - _Requirements: 8.4, NFR-1_

- [ ] 8.3 Note.com手動検証チェックリスト
  - 本番Note.comアカウントでのログイン確認
  - 下書き保存の実地検証（テスト記事使用）
  - セレクタの動作確認（Note.com UI変更時の対応手順）
  - 検証結果の記録テンプレート作成
  - ※CIでは自動実行しない（手動トリガー）
  - _Requirements: 6.1-6.9, NFR-3_

---

## Requirements Coverage Summary

| Requirement | Tasks |
|-------------|-------|
| 1.1-1.5 | 2.2, 2.5, 3.1, 3.2 |
| 2.1-2.6 | 4.1, 4.2 |
| 3.1-3.6 | 2.3, 3.3 |
| 4.1-4.8 | 5.1, 5.2, 6.1, 6.2, 6.3 |
| 5.1-5.6 | 3.4 |
| 6.1-6.9 | 7.1, 7.2, 7.3, 8.3 |
| 7.1-7.4 | 2.3, 2.4, 4.2 |
| 8.1-8.5 | 1.1, 2.1, 2.2, 2.3, 2.4, 8.2 |
| NFR-1 | 8.1, 8.2 |
| NFR-2 | 1.2, 7.1 |
| NFR-3 | 1.1, 8.3 |

---

## MVP Scope Notes

以下はMVP対象外としてタスクから除外：
- 音声ファイル入力（Req 3.4）
- 画像ファイル入力（Req 3.3）
- Note.comへの画像アップロード（Req 6.4の一部）

---

## Technical Decisions

| 項目 | 決定 | 理由 |
|------|------|------|
| LangGraph バージョン | 0.2.* 固定 | API安定性、StateGraph仕様の互換性 |
| ChromaDB パス | `data/chroma_db/` | .gitignore対象、Docker Volume対応 |
| 設定管理 | Pydantic Settings | 型安全、バリデーション、.env自動読み込み |
| Playwright セレクタ | data-testid優先 | DOM変更への耐性 |
| テスト戦略 | モックE2E + 手動検証分離 | CI実行可能性とNote.com依存の分離 |

---

## Seed Data Source

**記事候補マスター**: `91_RefDoc/02_生成AIとのやりとり履歴/05_記事候補.md`
- 60記事（Season 1-5）
- 週2本ペース（火: モヤモヤ型、金: 設計図型）
- フィールド: タイトル、会議の一言、結論3行、見出し案、図/表、持ち帰り、次に読む
