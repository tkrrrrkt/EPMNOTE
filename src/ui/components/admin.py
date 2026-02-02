"""
EPM Note Engine - Admin Components

Knowledge base management and system administration UI.
"""

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from src.repositories.rag_service import RAGService


# Field length limits based on Article model
FIELD_LIMITS = {
    "week_id": 50,
    "title": 255,
    "target_persona": 255,
    "seo_keywords": 255,
    "hook_statement": None,  # Text field, no limit
    "content_outline": None,  # Text field, no limit
}


@dataclass
class ValidationError:
    """Validation error with field name and message."""
    field: str
    message: str


@dataclass
class ArticleData:
    """Parsed article data for import."""
    week_id: str
    title: str
    target_persona: str | None = None
    hook_statement: str | None = None
    content_outline: str | None = None
    seo_keywords: str | None = None


def render_help_popover(label: str, body: str | list[str]) -> None:
    """Render a small help popover."""
    with st.popover(label):
        if isinstance(body, list):
            for line in body:
                st.markdown(f"- {line}")
        else:
            st.markdown(body)


def validate_article_data(
    data: ArticleData,
    existing_week_ids: set[str] | None = None,
) -> list[ValidationError]:
    """
    Validate article data against model constraints.

    Args:
        data: Article data to validate.
        existing_week_ids: Set of existing week IDs to check for duplicates.

    Returns:
        List of validation errors (empty if valid).
    """
    errors = []

    # Required fields
    if not data.week_id or not data.week_id.strip():
        errors.append(ValidationError("week_id", "Week ID は必須です"))
    elif len(data.week_id) > FIELD_LIMITS["week_id"]:
        errors.append(ValidationError(
            "week_id",
            f"Week ID は{FIELD_LIMITS['week_id']}文字以内にしてください（現在: {len(data.week_id)}文字）"
        ))
    elif existing_week_ids and data.week_id in existing_week_ids:
        errors.append(ValidationError("week_id", f"Week ID '{data.week_id}' は既に存在します"))

    if not data.title or not data.title.strip():
        errors.append(ValidationError("title", "タイトルは必須です"))
    elif len(data.title) > FIELD_LIMITS["title"]:
        errors.append(ValidationError(
            "title",
            f"タイトルは{FIELD_LIMITS['title']}文字以内にしてください（現在: {len(data.title)}文字）"
        ))

    # Optional fields with length limits
    if data.target_persona and len(data.target_persona) > FIELD_LIMITS["target_persona"]:
        errors.append(ValidationError(
            "target_persona",
            f"ターゲットペルソナは{FIELD_LIMITS['target_persona']}文字以内にしてください"
        ))

    if data.seo_keywords and len(data.seo_keywords) > FIELD_LIMITS["seo_keywords"]:
        errors.append(ValidationError(
            "seo_keywords",
            f"SEOキーワードは{FIELD_LIMITS['seo_keywords']}文字以内にしてください"
        ))

    return errors


def parse_markdown_articles(content: str) -> list[ArticleData]:
    """
    Parse markdown format article list.

    Expected format:
    ## Week1-1: タイトル
    - ターゲット: CFO, 経営企画
    - フック: 「会議の一言」
    - 見出し: 問題 → 原因 → 解決策
    - SEO: キーワード1, キーワード2

    Args:
        content: Markdown content to parse.

    Returns:
        List of parsed ArticleData.
    """
    articles = []

    # Pattern for article header: ## WeekX-Y: Title or ### N. Title
    # Also supports: ## WeekX-Y タイトル (without colon)
    header_pattern = re.compile(
        r"^##\s+(?:(\d+)\.\s+)?(?:(Week[\w-]+)[:\s]+)?(.+?)$",
        re.MULTILINE | re.IGNORECASE,
    )

    matches = list(header_pattern.finditer(content))

    for i, match in enumerate(matches):
        number = match.group(1)
        week_id = match.group(2)
        title = match.group(3).strip()

        # If no week_id but has number, generate week_id
        if not week_id and number:
            week_num = (int(number) + 1) // 2
            day_suffix = 1 if int(number) % 2 == 1 else 2
            week_id = f"Week{week_num}-{day_suffix}"
        elif not week_id:
            # Try to extract from title or use placeholder
            week_id = f"NEW-{i+1}"

        # Get section content
        start_pos = match.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        section = content[start_pos:end_pos]

        # Parse fields from section
        target = extract_markdown_field(section, ["ターゲット", "ペルソナ", "target", "persona"])
        hook = extract_markdown_field(section, ["フック", "会議", "hook", "導入"])
        outline = extract_markdown_field(section, ["見出し", "構成", "アウトライン", "outline"])
        seo = extract_markdown_field(section, ["SEO", "キーワード", "keyword"])

        articles.append(ArticleData(
            week_id=week_id,
            title=title,
            target_persona=target,
            hook_statement=hook,
            content_outline=outline,
            seo_keywords=seo,
        ))

    return articles


def extract_markdown_field(section: str, field_names: list[str]) -> str | None:
    """Extract a field value from markdown section."""
    for name in field_names:
        # Pattern: - field_name: value or - field_name：value
        pattern = re.compile(
            rf"^[-*]\s*{re.escape(name)}[：:]\s*(.+?)$",
            re.MULTILINE | re.IGNORECASE,
        )
        match = pattern.search(section)
        if match:
            value = match.group(1).strip()
            # Remove markdown formatting
            value = re.sub(r"\*\*([^*]+)\*\*", r"\1", value)
            value = re.sub(r"\*([^*]+)\*", r"\1", value)
            return value.strip() if value.strip() else None
    return None


def parse_json_articles(content: str) -> list[ArticleData]:
    """
    Parse JSON format article list.

    Expected format:
    [
      {
        "week_id": "Week1-1",
        "title": "タイトル",
        "target_persona": "CFO",
        "hook_statement": "フック",
        "content_outline": "見出し案",
        "seo_keywords": "キーワード"
      }
    ]

    Args:
        content: JSON content to parse.

    Returns:
        List of parsed ArticleData.
    """
    try:
        data = json.loads(content)
        if not isinstance(data, list):
            data = [data]

        articles = []
        for item in data:
            if isinstance(item, dict):
                articles.append(ArticleData(
                    week_id=str(item.get("week_id", "")),
                    title=str(item.get("title", "")),
                    target_persona=item.get("target_persona"),
                    hook_statement=item.get("hook_statement"),
                    content_outline=item.get("content_outline"),
                    seo_keywords=item.get("seo_keywords"),
                ))
        return articles
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON解析エラー: {e}")


def parse_tsv_articles(content: str) -> list[ArticleData]:
    """
    Parse TSV (Tab-Separated Values) format article list.
    This is the format when copying from Excel.

    Expected format (first row is header):
    week_id	title	target_persona	hook_statement	content_outline	seo_keywords
    Week1-1	タイトル1	CFO	フック1	見出し1	キーワード1
    Week1-2	タイトル2	経営企画	フック2	見出し2	キーワード2

    Args:
        content: TSV content to parse (copied from Excel).

    Returns:
        List of parsed ArticleData.
    """
    lines = content.strip().split("\n")
    if len(lines) < 2:
        raise ValueError("ヘッダー行とデータ行が必要です（最低2行）")

    # Parse header row to determine column mapping
    header = lines[0].split("\t")
    header_lower = [h.strip().lower() for h in header]

    # Column name mapping (flexible matching)
    column_mapping = {
        "week_id": ["week_id", "weekid", "week id", "週id", "週"],
        "title": ["title", "タイトル", "記事タイトル", "題名"],
        "target_persona": ["target_persona", "target", "persona", "ターゲット", "ペルソナ", "想定読者"],
        "hook_statement": ["hook_statement", "hook", "フック", "会議の一言", "導入"],
        "content_outline": ["content_outline", "outline", "見出し", "構成", "アウトライン"],
        "seo_keywords": ["seo_keywords", "seo", "keywords", "キーワード", "seoキーワード"],
    }

    # Find column indices
    col_indices = {}
    for field, aliases in column_mapping.items():
        for i, h in enumerate(header_lower):
            if h in aliases or any(alias in h for alias in aliases):
                col_indices[field] = i
                break

    # Require at least week_id and title
    if "week_id" not in col_indices:
        raise ValueError("Week ID 列が見つかりません。ヘッダー行に 'week_id' または '週ID' を含めてください。")
    if "title" not in col_indices:
        raise ValueError("タイトル列が見つかりません。ヘッダー行に 'title' または 'タイトル' を含めてください。")

    articles = []
    for i, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue

        cols = line.split("\t")

        def get_col(field: str) -> str | None:
            idx = col_indices.get(field)
            if idx is not None and idx < len(cols):
                val = cols[idx].strip()
                return val if val else None
            return None

        week_id = get_col("week_id") or ""
        title = get_col("title") or ""

        if not week_id and not title:
            continue  # Skip empty rows

        articles.append(ArticleData(
            week_id=week_id,
            title=title,
            target_persona=get_col("target_persona"),
            hook_statement=get_col("hook_statement"),
            content_outline=get_col("content_outline"),
            seo_keywords=get_col("seo_keywords"),
        ))

    return articles


def render_admin_panel() -> None:
    """Render the admin panel for knowledge base management."""
    st.header("管理パネル")

    tab1, tab2, tab3, tab4 = st.tabs(["記事管理", "知識ベース", "検索テスト", "システム情報"])

    with tab1:
        render_article_management_tab()

    with tab2:
        render_knowledge_base_tab()

    with tab3:
        render_search_test_tab()

    with tab4:
        render_system_info_tab()


def render_article_management_tab() -> None:
    """Render article management tab."""
    st.subheader("記事管理")

    # Three sections: Add, Bulk Import, and List
    add_section, import_section, list_section = st.tabs([
        "➕ 新規追加",
        "📥 一括取込",
        "📋 一覧・削除",
    ])

    with add_section:
        render_article_add_form()

    with import_section:
        render_article_import_form()

    with list_section:
        render_article_list()


def render_article_add_form() -> None:
    """Render form to add a new article."""
    from src.database.connection import get_session
    from src.database.models import Article, ArticleStatus
    from src.repositories.article_repository import ArticleRepository

    st.markdown("### 新規記事を追加")

    # Show field limits
    with st.expander("📏 入力制限", expanded=False):
        st.caption(f"- Week ID: 最大{FIELD_LIMITS['week_id']}文字")
        st.caption(f"- タイトル: 最大{FIELD_LIMITS['title']}文字")
        st.caption(f"- ターゲットペルソナ: 最大{FIELD_LIMITS['target_persona']}文字")
        st.caption(f"- SEOキーワード: 最大{FIELD_LIMITS['seo_keywords']}文字")

    with st.form(key="add_article_form"):
        # Required fields
        col1, col2 = st.columns(2)
        with col1:
            week_id = st.text_input(
                "Week ID *",
                placeholder="例: Week1-1",
                help=f"週番号と曜日（1=火曜, 2=金曜）- 最大{FIELD_LIMITS['week_id']}文字",
                max_chars=FIELD_LIMITS["week_id"],
            )
        with col2:
            title = st.text_input(
                "タイトル *",
                placeholder="例: 予実管理「数字が合わない」問題の正体",
                max_chars=FIELD_LIMITS["title"],
            )

        # Optional fields
        target_persona = st.text_input(
            "ターゲットペルソナ",
            placeholder="例: CFO, 経営企画",
            help="この記事の想定読者",
            max_chars=FIELD_LIMITS["target_persona"],
        )

        hook_statement = st.text_area(
            "フック（会議の一言）",
            placeholder="例: 「その数字、資料ごとに違うけど、どれが正しいの？」",
            help="読者の注意を引く一言",
            height=80,
        )

        content_outline = st.text_area(
            "見出し案",
            placeholder="例: 問題の本質 → 3つの原因 → 解決アプローチ → 具体的なステップ",
            help="記事の構成案（→で区切る）",
            height=100,
        )

        seo_keywords = st.text_input(
            "SEOキーワード",
            placeholder="例: 予実管理, 数字が合わない, 経営管理",
            help="カンマ区切りで複数入力可能（後からリサーチ時に設定も可）",
            max_chars=FIELD_LIMITS["seo_keywords"],
        )

        submitted = st.form_submit_button(
            "📝 記事を追加",
            type="primary",
            use_container_width=True,
        )

        if submitted:
            try:
                with get_session() as session:
                    repo = ArticleRepository(session)

                    # Get existing week IDs for duplicate check
                    existing_week_ids = {a.week_id for a in repo.get_all()}

                    # Validate using shared validation function
                    article_data = ArticleData(
                        week_id=week_id,
                        title=title,
                        target_persona=target_persona or None,
                        hook_statement=hook_statement or None,
                        content_outline=content_outline or None,
                        seo_keywords=seo_keywords or None,
                    )
                    errors = validate_article_data(article_data, existing_week_ids)

                    if errors:
                        for error in errors:
                            st.error(f"❌ {error.field}: {error.message}")
                    else:
                        # Create new article
                        article = Article(
                            week_id=week_id,
                            title=title,
                            target_persona=target_persona or None,
                            hook_statement=hook_statement or None,
                            content_outline=content_outline or None,
                            seo_keywords=seo_keywords or None,
                            status=ArticleStatus.PLANNING,
                        )
                        repo.create(article)
                        session.commit()
                        st.success(f"✅ 記事を追加しました: {title}")
                        st.rerun()
            except Exception as e:
                st.error(f"追加に失敗しました: {e}")


def render_article_import_form() -> None:
    """Render bulk import form for articles."""
    from src.database.connection import get_session
    from src.database.models import Article, ArticleStatus
    from src.repositories.article_repository import ArticleRepository

    st.markdown("### 一括取込")

    # Format selection
    format_type = st.radio(
        "入力形式",
        ["Excel (コピペ)", "Markdown", "JSON"],
        horizontal=True,
        help="Excelからコピー、生成AIの出力形式に合わせて選択",
    )

    # Show format examples
    with st.expander("📝 入力形式の例", expanded=False):
        if format_type == "Excel (コピペ)":
            st.markdown("""
**Excel形式** - Excelで記事リストを管理している場合に便利

1. 以下のヘッダー行を含むExcelファイルを作成：

| week_id | title | target_persona | hook_statement | content_outline | seo_keywords |
|---------|-------|----------------|----------------|-----------------|--------------|
| Week1-1 | タイトル1 | CFO | フック1 | 見出し1 | キーワード1 |
| Week1-2 | タイトル2 | 経営企画 | フック2 | 見出し2 | キーワード2 |

2. データ部分（ヘッダー含む）を選択してコピー (Ctrl+C)
3. 下のテキストエリアに貼り付け (Ctrl+V)

**ヘッダー名は柔軟に対応:**
- `week_id`, `週ID`, `Week ID` → Week ID
- `title`, `タイトル` → タイトル
- `target_persona`, `ターゲット`, `ペルソナ` → ターゲット
- `hook_statement`, `フック`, `会議の一言` → フック
- `content_outline`, `見出し`, `構成` → 見出し
- `seo_keywords`, `SEO`, `キーワード` → SEOキーワード
            """)
        elif format_type == "Markdown":
            st.markdown("""
**Markdown形式** - 生成AIに記事候補を作ってもらう場合に便利

```markdown
## Week1-1: 予実管理「数字が合わない」問題の正体
- ターゲット: CFO, 経営企画
- フック: 「その数字、どれが正しいの？」
- 見出し: 問題の本質 → 3つの原因 → 解決策
- SEO: 予実管理, 数字, 経営管理

## Week1-2: KPI設計の落とし穴
- ターゲット: 事業部長, FP&A
- フック: 「KPIを設定したのに成果が出ない」
- 見出し: よくある失敗 → 正しい設計手順 → 運用のコツ
- SEO: KPI, 設計, 経営指標
```

または番号形式:
```markdown
## 1. 予実管理「数字が合わない」問題の正体
- ターゲット: CFO

## 2. KPI設計の落とし穴
- ターゲット: 事業部長
```
            """)
        else:
            st.markdown("""
**JSON形式** - プログラム的に生成する場合に便利

```json
[
  {
    "week_id": "Week1-1",
    "title": "予実管理「数字が合わない」問題の正体",
    "target_persona": "CFO, 経営企画",
    "hook_statement": "「その数字、どれが正しいの？」",
    "content_outline": "問題の本質 → 3つの原因 → 解決策",
    "seo_keywords": "予実管理, 数字, 経営管理"
  },
  {
    "week_id": "Week1-2",
    "title": "KPI設計の落とし穴",
    "target_persona": "事業部長, FP&A"
  }
]
```
            """)

    # Input area
    import_content = st.text_area(
        "データを貼り付け",
        height=300,
        placeholder="上記の形式でデータを貼り付けてください...",
        key="import_content",
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🔍 プレビュー", use_container_width=True):
            if not import_content.strip():
                st.warning("データを入力してください")
            else:
                try:
                    # Parse based on format
                    if format_type == "Excel (コピペ)":
                        articles = parse_tsv_articles(import_content)
                    elif format_type == "Markdown":
                        articles = parse_markdown_articles(import_content)
                    else:
                        articles = parse_json_articles(import_content)

                    if not articles:
                        st.warning("記事が見つかりませんでした。形式を確認してください。")
                    else:
                        st.session_state["preview_articles"] = articles
                        st.success(f"✅ {len(articles)} 件の記事を検出しました")
                except Exception as e:
                    st.error(f"解析エラー: {e}")

    # Show preview if available
    if "preview_articles" in st.session_state and st.session_state["preview_articles"]:
        articles = st.session_state["preview_articles"]

        st.divider()
        st.markdown("#### プレビュー")

        try:
            with get_session() as session:
                repo = ArticleRepository(session)
                existing_week_ids = {a.week_id for a in repo.get_all()}

                valid_articles = []
                has_errors = False

                for i, article in enumerate(articles):
                    errors = validate_article_data(article, existing_week_ids)

                    with st.expander(
                        f"{'❌' if errors else '✅'} {article.week_id}: {article.title[:40]}...",
                        expanded=bool(errors),
                    ):
                        if errors:
                            has_errors = True
                            for error in errors:
                                st.error(f"{error.field}: {error.message}")
                        else:
                            valid_articles.append(article)

                        st.markdown(f"**ターゲット:** {article.target_persona or '(未設定)'}")
                        st.markdown(f"**フック:** {article.hook_statement or '(未設定)'}")
                        st.markdown(f"**見出し:** {article.content_outline or '(未設定)'}")
                        st.markdown(f"**SEO:** {article.seo_keywords or '(未設定)'}")

                st.divider()

                # Import button
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("有効", f"{len(valid_articles)} 件")
                with col2:
                    st.metric("エラー", f"{len(articles) - len(valid_articles)} 件")

                if valid_articles:
                    if st.button(
                        f"📥 {len(valid_articles)} 件を取込",
                        type="primary",
                        use_container_width=True,
                    ):
                        imported = 0
                        for article_data in valid_articles:
                            article = Article(
                                week_id=article_data.week_id,
                                title=article_data.title,
                                target_persona=article_data.target_persona,
                                hook_statement=article_data.hook_statement,
                                content_outline=article_data.content_outline,
                                seo_keywords=article_data.seo_keywords,
                                status=ArticleStatus.PLANNING,
                            )
                            repo.create(article)
                            imported += 1

                        session.commit()
                        st.success(f"✅ {imported} 件の記事を取り込みました！")
                        del st.session_state["preview_articles"]
                        st.rerun()
                else:
                    st.warning("取り込める記事がありません。エラーを修正してください。")

        except Exception as e:
            st.error(f"エラー: {e}")


def render_article_list() -> None:
    """Render list of existing articles with delete option."""
    from src.database.connection import get_session
    from src.database.models import ArticleStatus
    from src.repositories.article_repository import ArticleRepository

    st.markdown("### 既存記事一覧")

    try:
        with get_session() as session:
            repo = ArticleRepository(session)
            articles = list(repo.get_all())

            if not articles:
                st.info("記事がありません")
                return

            st.caption(f"全 {len(articles)} 件")

            # Status filter
            status_filter = st.selectbox(
                "ステータスで絞り込み",
                options=["すべて"] + [s.value for s in ArticleStatus],
                key="admin_status_filter",
            )

            if status_filter != "すべて":
                articles = [a for a in articles if a.status.value == status_filter]

            # Display articles
            for article in articles:
                with st.expander(f"**{article.week_id}** - {article.title[:40]}..."):
                    col1, col2 = st.columns([3, 1])

                    with col1:
                        st.markdown(f"**ステータス:** {article.status.value}")
                        if article.target_persona:
                            st.markdown(f"**ターゲット:** {article.target_persona}")
                        if article.seo_keywords:
                            st.markdown(f"**SEOキーワード:** {article.seo_keywords}")
                        if article.hook_statement:
                            st.markdown(f"**フック:** {article.hook_statement[:100]}...")
                        st.caption(f"作成日: {article.created_at.strftime('%Y-%m-%d %H:%M')}")

                    with col2:
                        # Delete button with confirmation
                        delete_key = f"delete_{article.id}"
                        confirm_key = f"confirm_delete_{article.id}"

                        if st.session_state.get(confirm_key):
                            st.warning("本当に削除しますか？")
                            col_yes, col_no = st.columns(2)
                            with col_yes:
                                if st.button("はい", key=f"yes_{article.id}"):
                                    repo.delete(article.id)
                                    session.commit()
                                    st.session_state[confirm_key] = False
                                    st.success("削除しました")
                                    st.rerun()
                            with col_no:
                                if st.button("いいえ", key=f"no_{article.id}"):
                                    st.session_state[confirm_key] = False
                                    st.rerun()
                        else:
                            if st.button("🗑️ 削除", key=delete_key, use_container_width=True):
                                st.session_state[confirm_key] = True
                                st.rerun()

    except Exception as e:
        st.error(f"記事の読み込みに失敗: {e}")


def render_knowledge_base_tab() -> None:
    """Render knowledge base management tab."""
    st.subheader("知識ベース管理")

    try:
        rag_service = RAGService()

        # Show current stats
        kb_count = rag_service.get_collection_count("knowledge_base")
        archive_count = rag_service.get_collection_count("archive_index")
        embedding_info = rag_service.get_embedding_info()

        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            st.metric("knowledge_base", f"{kb_count} チャンク")
        with col2:
            st.metric("archive_index", f"{archive_count} チャンク")
        with col3:
            render_help_popover(
                "ℹ️",
                [
                    "knowledge_base = 91_RefDoc の資料から作る知識ベース",
                    "archive_index = DBの過去記事/スニペットから作る知識ベース",
                    "チャンク数は検索対象の分割数",
                ],
            )
        st.caption(f"Embedding: {embedding_info.get('provider')} / {embedding_info.get('model')}")
        render_help_popover(
            "ℹ️ Embeddingとは？",
            "文章を検索しやすい数値ベクトルに変換するAIモデルです。",
        )

        st.divider()

        # Seed knowledge base section
        st.subheader("91_RefDoc からの投入")
        render_help_popover(
            "ℹ️ ここで何をする？",
            [
                "91_RefDoc のファイルを読み込み、knowledge_base に反映します。",
                "アーカイブ更新は DB の記事/スニペットを archive_index に反映します。",
            ],
        )

        ref_doc_path = Path(__file__).parent.parent.parent.parent / "91_RefDoc"
        if ref_doc_path.exists():
            file_count = (
                len(list(ref_doc_path.rglob("*.md")))
                + len(list(ref_doc_path.rglob("*.txt")))
                + len(list(ref_doc_path.rglob("*.json")))
                + len(list(ref_doc_path.rglob("*.pdf")))
            )
            st.info(f"📁 {ref_doc_path} に {file_count} 件のファイルがあります")
        else:
            st.warning(f"⚠️ {ref_doc_path} が見つかりません")

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("ドライラン（確認のみ）", use_container_width=True):
                with st.spinner("ファイルをスキャン中..."):
                    result = run_seed_script("seed_knowledge_base.py", dry_run=True)
                    st.code(result, language="text")
            render_help_popover(
                "ℹ️ ドライラン",
                "実際の更新はせず、読み込める件数だけ確認します。",
            )

        with col2:
            if st.button("知識ベースを更新", type="primary", use_container_width=True):
                with st.spinner("知識ベースを更新中..."):
                    result = run_seed_script("seed_knowledge_base.py", dry_run=False, extra_args=["--prune-missing"])
                    st.code(result, language="text")
                    st.success("更新完了！ページを再読み込みしてください。")
            render_help_popover(
                "ℹ️ 知識ベース更新",
                "91_RefDoc の内容を knowledge_base に反映します（削除されたファイルは除外）。",
            )

        with col3:
            if st.button("アーカイブを更新", use_container_width=True):
                with st.spinner("archive_index を更新中..."):
                    result = run_seed_script("seed_archive_index.py", dry_run=False, extra_args=["--prune-missing"])
                    st.code(result, language="text")
                    st.success("archive_index の更新完了！")
            render_help_popover(
                "ℹ️ アーカイブ更新",
                "DBの過去記事/スニペットを archive_index に反映します。",
            )

        if st.button("RAG更新（知識ベース + アーカイブ）", use_container_width=True):
            with st.spinner("RAGを更新中..."):
                kb_result = run_seed_script("seed_knowledge_base.py", dry_run=False, extra_args=["--prune-missing"])
                ar_result = run_seed_script("seed_archive_index.py", dry_run=False, extra_args=["--prune-missing"])
                st.code(kb_result + "\n" + ar_result, language="text")
                st.success("RAG更新完了！ページを再読み込みしてください。")
        render_help_popover(
            "ℹ️ RAG更新",
            "知識ベース更新 + アーカイブ更新をまとめて実行します。",
        )

        st.divider()

        # Clear collections
        st.subheader("データクリア")
        render_help_popover(
            "ℹ️ クリアとは？",
            "ChromaDBの検索用データだけを削除します。元ファイルやDBは消えません。",
        )
        st.warning("⚠️ この操作は取り消せません")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("knowledge_base をクリア", use_container_width=True):
                if st.session_state.get("confirm_clear_kb"):
                    rag_service.clear_collection("knowledge_base")
                    st.success("knowledge_base をクリアしました")
                    st.session_state.confirm_clear_kb = False
                else:
                    st.session_state.confirm_clear_kb = True
                    st.warning("もう一度クリックして確定")
            render_help_popover(
                "ℹ️ knowledge_base クリア",
                "91_RefDoc 由来のRAGデータを削除します。",
            )

        with col2:
            if st.button("archive_index をクリア", use_container_width=True):
                if st.session_state.get("confirm_clear_archive"):
                    rag_service.clear_collection("archive_index")
                    st.success("archive_index をクリアしました")
                    st.session_state.confirm_clear_archive = False
                else:
                    st.session_state.confirm_clear_archive = True
                    st.warning("もう一度クリックして確定")
            render_help_popover(
                "ℹ️ archive_index クリア",
                "DB由来のRAGデータを削除します。",
            )

    except Exception as e:
        st.error(f"RAGサービスの初期化に失敗: {e}")


def render_search_test_tab() -> None:
    """Render search test tab for RAG quality verification."""
    st.subheader("RAG検索テスト")

    query = st.text_input("検索クエリ", placeholder="例: 予実管理 KPI設計")
    top_k = st.slider("取得件数", min_value=1, max_value=20, value=5)
    generate_answer = st.checkbox("生成AIで回答を作成")
    provider = st.radio("モデル", ["Anthropic", "OpenAI"], horizontal=True) if generate_answer else None

    collection = st.radio(
        "検索対象",
        ["knowledge_base", "archive_index"],
        horizontal=True,
    )

    if st.button("検索", type="primary") and query:
        try:
            rag_service = RAGService()
            results = rag_service.search(collection, query, top_k=top_k)

            if results:
                st.success(f"{len(results)} 件の結果")

                for i, result in enumerate(results, 1):
                    with st.expander(f"#{i} - 距離: {result.distance:.4f}"):
                        st.markdown(f"**ID:** `{result.id}`")
                        st.markdown(f"**メタデータ:** `{result.metadata}`")
                        st.divider()
                        st.markdown(result.content[:500] + "..." if len(result.content) > 500 else result.content)
            else:
                st.warning("結果が見つかりませんでした")

            if generate_answer and results:
                st.divider()
                st.markdown("### 生成回答（RAG）")
                try:
                    answer = generate_rag_answer(query, results, provider or "Anthropic")
                    st.markdown(answer)
                except Exception as e:
                    st.error(f"生成回答エラー: {e}")

        except Exception as e:
            st.error(f"検索エラー: {e}")


def generate_rag_answer(query: str, results: list, provider: str) -> str:
    """Generate an answer using retrieved RAG results."""
    # Build compact context
    context_parts = []
    for i, r in enumerate(results, 1):
        snippet = r.content[:800] if r.content else ""
        context_parts.append(f"[{i}] {snippet}")
    context = "\n\n".join(context_parts)

    prompt = f"""以下の検索結果を使って、質問に回答してください。
出典は必ず [番号] で引用してください（例: [1], [2]）。

## 質問
{query}

## 検索結果
{context}

## 回答
"""

    if provider == "OpenAI":
        from src.config import get_openai_client
        client = get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "あなたは経営管理・FP&Aの専門家です。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=800,
        )
        return response.choices[0].message.content or ""

    from src.config import get_anthropic_client
    client = get_anthropic_client()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text if response.content else ""


def render_system_info_tab() -> None:
    """Render system information tab."""
    st.subheader("システム情報")

    # Database status
    st.markdown("### PostgreSQL")
    try:
        from src.database.connection import get_session
        from src.repositories.article_repository import ArticleRepository

        with get_session() as session:
            repo = ArticleRepository(session)
            articles = repo.get_all()
            st.success(f"✅ 接続OK - {len(articles)} 件の記事")
    except Exception as e:
        st.error(f"❌ 接続エラー: {e}")

    # ChromaDB status
    st.markdown("### ChromaDB")
    try:
        rag_service = RAGService()
        st.success(f"✅ 接続OK - パス: {rag_service.client._persist_directory}")
    except Exception as e:
        st.error(f"❌ 接続エラー: {e}")

    # Environment info
    st.markdown("### 環境変数")
    from src.config import get_settings
    try:
        settings = get_settings()
        env_status = {
            "DATABASE_URL": "✅" if settings.database_url else "❌",
            "ANTHROPIC_API_KEY": "✅" if settings.anthropic_api_key else "❌",
            "OPENAI_API_KEY": "✅" if settings.openai_api_key else "❌",
            "TAVILY_API_KEY": "✅" if settings.tavily_api_key else "❌",
            "NOTE_EMAIL": "✅" if settings.note_email else "❌",
        }
        for key, status in env_status.items():
            st.text(f"{status} {key}")
    except Exception as e:
        st.error(f"設定読み込みエラー: {e}")


def run_seed_script(script_name: str, dry_run: bool = False, extra_args: list[str] | None = None) -> str:
    """Run a seeding script under scripts/."""
    script_path = Path(__file__).parent.parent.parent.parent / "scripts" / script_name

    cmd = [sys.executable, str(script_path)]
    if dry_run:
        cmd.append("--dry-run")
    if extra_args:
        cmd.extend(extra_args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**dict(**os.environ), "PYTHONIOENCODING": "utf-8"},
            timeout=300,
            cwd=script_path.parent.parent,
        )
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return "タイムアウト: 処理に時間がかかりすぎています"
    except Exception as e:
        return f"エラー: {e}"
