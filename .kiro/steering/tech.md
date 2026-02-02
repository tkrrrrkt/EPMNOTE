# Technology Stack

## Architecture

**Autonomous Marketing RAG with Last-Mile Automation**

- Streamlit による対話的UI
- LangGraph による状態管理付きAIワークフロー
- PostgreSQL + ChromaDB のハイブリッドデータストア
- Playwright によるブラウザ自動化

## Core Technologies

- **Language**: Python 3.10+
- **Framework**: Streamlit（UI）, LangChain / LangGraph（AIワークフロー）
- **Database**: PostgreSQL 15+（RDB）, ChromaDB（Vector Store）
- **ORM**: SQLAlchemy（Async対応推奨）
- **Automation**: Playwright（Headless Browser）

## Key Libraries

| 用途 | ライブラリ |
|------|-----------|
| UI | Streamlit |
| AIワークフロー | LangChain, LangGraph |
| Vector Store | ChromaDB (Persistent Client) |
| RDB | PostgreSQL + SQLAlchemy |
| ブラウザ自動化 | Playwright |
| Web検索 | Tavily API |

## AI Model Configuration

| 用途 | モデル |
|------|-------|
| Main（執筆・ロジック） | Anthropic Claude 3.5 Sonnet |
| Sub（検索・マルチモーダル） | OpenAI GPT-4o |

**原則**: AIは道具。最終判断・公開決定は人間が行う。

## Development Standards

### 環境変数管理

```bash
# .env.example に定義（実値は .env に記載、.gitignore対象）
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
TAVILY_API_KEY=
NOTE_EMAIL=          # Note.com ログイン用
NOTE_PASSWORD=       # Note.com ログイン用（セキュリティ注意）
DATABASE_URL=        # PostgreSQL接続文字列
```

**セキュリティ**: 認証情報は絶対にコミットしない。

### コード品質

- Type Hints を積極的に使用
- Docstring で関数の目的を明記
- Ruff / Black によるフォーマット統一（推奨）

## Development Environment

### Required Tools

- Python 3.10+
- Docker / Docker Compose（PostgreSQL用）
- Node.js（Playwright用）

### Common Commands

```bash
# 環境構築
pip install -r requirements.txt
playwright install

# DB起動
docker-compose up -d

# アプリ起動
streamlit run app.py
```

## Key Technical Decisions

1. **Streamlit選択理由**: プロトタイピング速度優先、1人〜少人数運用想定
2. **LangGraph選択理由**: 状態管理付きワークフロー、Self-Correctionループの実装容易性
3. **PostgreSQL + ChromaDB**: 構造化データ（記事管理）+ ベクトル検索（RAG）の両立
4. **Playwright選択理由**: Note.comへの下書き保存自動化（API非公開のため）

---
_Document standards and patterns, not every dependency_
