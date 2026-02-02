# Research & Design Decisions

---
**Purpose**: EPM Note Engineの技術設計に必要な調査・意思決定を記録する。
---

## Summary
- **Feature**: `epm-note-engine`
- **Discovery Scope**: New Feature (Greenfield)
- **Key Findings**:
  1. LangGraphはStateful Workflowに最適で、Self-Correctionループの実装が容易
  2. StreamlitはPython単体でUI構築可能、プロトタイピング速度が高い
  3. PlaywrightはNote.comのような動的サイトの自動化に適している

## Research Log

### LangGraph Workflow Design
- **Context**: 記事生成→レビュー→修正のループを状態管理付きで実装する必要がある
- **Sources Consulted**:
  - LangGraph公式ドキュメント
  - LangChain Expression Language (LCEL) ドキュメント
- **Findings**:
  - LangGraphはStateGraphを使用してノード間の状態遷移を定義
  - Conditional edgeで分岐条件（スコア < 80点）を実装可能
  - 状態はTypedDictで型安全に管理可能
- **Implications**:
  - Research → Draft → Review → (Correction) → Complete のフロー設計
  - StateにはArticleの全情報を保持

### Streamlit UI Architecture
- **Context**: 記事管理のUIをPythonのみで構築する
- **Sources Consulted**:
  - Streamlit公式ドキュメント
  - Streamlit session_state管理
- **Findings**:
  - session_stateで画面間の状態を保持
  - st.file_uploaderで画像・音声のドラッグ＆ドロップ対応
  - st.sidebarで記事一覧を常時表示可能
- **Implications**:
  - マルチページ構成ではなく、session_stateベースの画面遷移
  - sidebar + main contentのレイアウト

### Playwright Note.com Automation
- **Context**: Note.comへの下書き保存を自動化する
- **Sources Consulted**:
  - Playwright Python公式ドキュメント
  - Note.comのログインフロー調査
- **Findings**:
  - Note.comはメール/パスワードでログイン可能
  - 投稿画面はJavaScriptで動的に生成される
  - 下書き保存ボタンのセレクタ特定が必要
- **Implications**:
  - Headless modeで実行、エラー時はスクリーンショット取得
  - ログインセッションのCookie保存で再ログイン回避を検討

### ChromaDB Vector Store Design
- **Context**: 社内資料と過去記事のRAG検索を実装する
- **Sources Consulted**:
  - ChromaDB公式ドキュメント
  - Persistent Client設定
- **Findings**:
  - Persistent Clientで`data/chroma_db/`に永続化
  - Collectionは用途別に分離（knowledge_base, archive_index）
  - OpenAI Embeddingまたはローカルモデル選択可能
- **Implications**:
  - 2つのCollectionを使い分け
  - Embedding modelはOpenAI text-embedding-3-smallを使用

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Layered (採用) | UI → Logic → Database の3層構成 | シンプル、Streamlitと相性良い | スケール時に再設計必要 | steering/structure.mdに準拠 |
| Hexagonal | Ports & Adaptersパターン | テスト容易、依存逆転 | 過剰設計、1人開発では重い | 将来拡張時に検討 |

## Design Decisions

### Decision: AI Model Selection
- **Context**: 記事生成とマルチモーダル処理に使用するモデル選択
- **Alternatives Considered**:
  1. Claude 3.5 Sonnet のみ
  2. GPT-4o のみ
  3. Claude（執筆） + GPT-4o（検索・マルチモーダル）のハイブリッド
- **Selected Approach**: ハイブリッド（Option 3）
- **Rationale**: Claudeは長文生成に強く、GPT-4oはTavily連携・画像理解に優れる
- **Trade-offs**: 2つのAPIキー管理が必要、コスト増
- **Follow-up**: 実運用でのコスト・品質バランスを検証

### Decision: State Management Strategy
- **Context**: LangGraphの状態とStreamlitのsession_stateの役割分担
- **Alternatives Considered**:
  1. LangGraphの状態をDBに永続化
  2. session_stateで一時管理、完了時にDB保存
  3. 両方を併用
- **Selected Approach**: session_stateで一時管理、フェーズ完了時にDB保存（Option 2）
- **Rationale**: シンプルさ優先、DBアクセス頻度を減らす
- **Trade-offs**: ブラウザリロードで進行中の状態が失われる可能性
- **Follow-up**: 重要な状態変更時は即時DB保存を検討

### Decision: Error Handling for Playwright
- **Context**: Note.com自動投稿の失敗時対応
- **Alternatives Considered**:
  1. 失敗時は即エラー表示のみ
  2. 自動リトライ（最大3回）
  3. スクリーンショット保存 + 手動リトライUI
- **Selected Approach**: スクリーンショット保存 + 手動リトライUI（Option 3）
- **Rationale**: デバッグ容易性、ユーザー制御権の確保
- **Trade-offs**: 自動復旧なし、ユーザー操作が必要
- **Follow-up**: 頻発するエラーパターンがあれば自動リトライ追加

## Risks & Mitigations
- **Note.comのUI変更リスク** — Playwrightセレクタの定期検証、変更時は速やかに対応
- **APIコスト超過リスク** — 使用量モニタリング、生成回数の上限設定を検討
- **認証情報漏洩リスク** — 環境変数管理徹底、.envは.gitignore対象

## References
- [LangGraph Documentation](https://python.langchain.com/docs/langgraph) — Stateful Workflow実装
- [Streamlit Documentation](https://docs.streamlit.io/) — UI構築
- [Playwright Python](https://playwright.dev/python/) — ブラウザ自動化
- [ChromaDB](https://docs.trychroma.com/) — Vector Store
- [Tavily API](https://tavily.com/) — Web検索API
