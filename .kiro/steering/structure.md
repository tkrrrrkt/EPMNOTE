# Project Structure

## Organization Philosophy

**機能別モジュール構成** - Streamlit + Python の特性に合わせたシンプルな構造

- `logic/` に AIワークフロー・ビジネスロジックを集約
- `ui/` に Streamlit UIコンポーネントを集約
- `database/` に DB関連を集約
- `data/` に入出力ファイル・永続データを集約

## Directory Patterns

### Entry Point
**Location**: `app.py`
**Purpose**: Streamlit アプリケーションのエントリポイント
**Example**: `streamlit run app.py`

### AI Workflow Logic
**Location**: `logic/`
**Purpose**: LangGraph ワークフロー、エージェント、RAG処理
**Files**:
- `graph.py` - LangGraph メインワークフロー
- `agents.py` - Research, Writer, Reviewer エージェント
- `rag.py` - ChromaDB 検索ロジック
- `multimodal.py` - 画像/音声処理
- `automation.py` - Playwright Note自動投稿

### UI Components
**Location**: `ui/`
**Purpose**: Streamlit 画面コンポーネント
**Files**:
- `sidebar.py` - 記事選択サイドバー
- `input_form.py` - エッセンス入力フォーム
- `editor.py` - 記事エディタ・アップロードボタン
- `components.py` - 共通UIパーツ

### Database
**Location**: `database/`
**Purpose**: SQLAlchemy モデル、DB接続管理
**Files**:
- `models.py` - SQLAlchemy テーブル定義
- `database.py` - DB Session 管理

### Data Files
**Location**: `data/`
**Purpose**: 入出力ファイル・永続データ
**Subdirs**:
- `inputs/knowledge/` - RAG用社内資料
- `inputs/uploads/` - ユーザーアップロードファイル
- `inputs/candidates.md` - 記事候補リスト
- `outputs/` - 完成記事（Markdown）
- `chroma_db/` - ChromaDB 永続化

### Configuration
**Location**: `config.py`
**Purpose**: 環境変数・設定値の一元管理

## Naming Conventions

- **Files**: snake_case（Python標準）
- **Classes**: PascalCase
- **Functions/Variables**: snake_case
- **Constants**: UPPER_SNAKE_CASE

## Import Organization

```python
# 1. 標準ライブラリ
import os
from pathlib import Path

# 2. サードパーティ
import streamlit as st
from langchain_anthropic import ChatAnthropic
from sqlalchemy import create_engine

# 3. ローカルモジュール
from logic.graph import run_workflow
from database.models import Article
from ui.components import render_header
```

## Code Organization Principles

1. **logic/ は UI に依存しない**: ロジックは Streamlit なしでテスト可能に
2. **database/ は logic/ から利用**: UI → logic → database の依存方向
3. **config.py で環境変数を集約**: 各モジュールは config 経由でアクセス
4. **data/ はコミット対象外**: `.gitignore` で除外（chroma_db/, uploads/ 等）

## SSoT (Single Source of Truth)

| 対象 | 正本 |
|------|------|
| プロダクト方針 | `.kiro/steering/product.md` |
| 技術方針 | `.kiro/steering/tech.md` |
| 構造方針 | `.kiro/steering/structure.md`（本ファイル） |
| 詳細仕様 | `91_RefDoc/00_自動化システム仕様概要/仕様概要.md` |

---
_Document patterns, not file trees. New files following patterns shouldn't require updates_
