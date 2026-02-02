"""
EPM Note Engine - Input Form Component

Essence (snippet) input for article generation.
"""

import streamlit as st

from src.database.models import Article, Snippet, SnippetCategory
from src.ui.state import SessionState, UIPhase


# Category display info
CATEGORY_INFO = {
    SnippetCategory.FAILURE: {
        "label": "失敗談",
        "icon": "💥",
        "description": "失敗経験、つまずいたポイント、学んだ教訓",
        "placeholder": "例: かつて予実管理を導入した際、定義を曖昧にしたまま進めてしまい...",
    },
    SnippetCategory.OPINION: {
        "label": "意見・主張",
        "icon": "💭",
        "description": "独自の視点、業界への提言、差別化ポイント",
        "placeholder": "例: 多くの企業が見落としているのは、数字の「定義」ではなく「運用」だと考えます...",
    },
    SnippetCategory.TECH: {
        "label": "技術知見",
        "icon": "🔧",
        "description": "専門的なノウハウ、具体的な手法、ツールの使い方",
        "placeholder": "例: 指標辞書を作成する際は、まず「誰が」「何の意思決定に」使うかを明確にします...",
    },
    SnippetCategory.HOOK: {
        "label": "フック・導入",
        "icon": "🎣",
        "description": "読者の興味を引く導入、共感を呼ぶエピソード",
        "placeholder": "例: 「その数字、資料ごとに違うけど、どれが正しいの？」という会議での一言...",
    },
}


def render_input_form(
    article: Article,
    existing_snippets: list[Snippet],
    on_submit: callable = None,
    on_skip: callable = None,
) -> list[dict]:
    """
    Render the essence input form.

    Args:
        article: The article being edited.
        existing_snippets: List of existing snippets for this article.
        on_submit: Callback when form is submitted.
        on_skip: Callback when user skips input.

    Returns:
        List of new snippet data dictionaries.
    """
    st.header("✏️ エッセンス入力")
    st.markdown(f"**記事:** {article.title}")

    # Research summary display
    if article.research_summary:
        with st.expander("🔍 リサーチ結果", expanded=False):
            st.markdown(article.research_summary)

    st.divider()

    # Existing snippets
    if existing_snippets:
        st.subheader("📝 入力済みエッセンス")
        for snippet in existing_snippets:
            render_snippet_card(snippet)
        st.divider()

    # New snippet input
    st.subheader("➕ 新しいエッセンスを追加")

    new_snippets = []

    # Category tabs
    tabs = st.tabs([f"{info['icon']} {info['label']}" for info in CATEGORY_INFO.values()])

    for i, (category, info) in enumerate(CATEGORY_INFO.items()):
        with tabs[i]:
            st.caption(info["description"])

            with st.form(key=f"snippet_form_{category.value}"):
                content = st.text_area(
                    "内容",
                    placeholder=info["placeholder"],
                    height=150,
                    key=f"content_{category.value}",
                )

                tags_input = st.text_input(
                    "タグ（カンマ区切り）",
                    placeholder="例: 予実管理, 定義, 運用",
                    key=f"tags_{category.value}",
                )

                col1, col2 = st.columns([1, 1])
                with col1:
                    submitted = st.form_submit_button(
                        f"{info['icon']} 追加",
                        type="primary",
                        use_container_width=True,
                    )

                if submitted and content:
                    tags = [t.strip() for t in tags_input.split(",") if t.strip()]
                    new_snippets.append({
                        "category": category,
                        "content": content,
                        "tags": tags,
                    })
                    st.success(f"{info['label']}を追加しました！")

    st.divider()

    # Action buttons
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        if st.button("📝 下書き生成を開始", type="primary", use_container_width=True):
            if on_submit:
                on_submit(new_snippets)
            SessionState.set_ui_phase(UIPhase.DRAFTING)
            st.rerun()

    with col2:
        total_snippets = len(existing_snippets) + len(new_snippets)
        if total_snippets == 0:
            if st.button("⏭️ スキップ（エッセンスなし）", use_container_width=True):
                if on_skip:
                    on_skip()
                SessionState.set_ui_phase(UIPhase.DRAFTING)
                st.rerun()

    with col3:
        if st.button("🔙 記事選択に戻る", use_container_width=True):
            SessionState.set_ui_phase(UIPhase.ARTICLE_SELECT)
            st.rerun()

    return new_snippets


def render_snippet_card(snippet: Snippet) -> None:
    """
    Render a card displaying an existing snippet.

    Args:
        snippet: The snippet to display.
    """
    info = CATEGORY_INFO.get(snippet.category, {"icon": "📄", "label": "その他"})

    with st.container():
        col1, col2 = st.columns([1, 9])

        with col1:
            st.write(info["icon"])

        with col2:
            st.markdown(f"**{info['label']}**")
            st.write(snippet.content[:200] + "..." if len(snippet.content) > 200 else snippet.content)

            if snippet.tags:
                tags_html = " ".join([f"`{tag}`" for tag in snippet.tags])
                st.markdown(tags_html)


def render_essence_summary(snippets: list[Snippet]) -> None:
    """
    Render a summary of all snippets for an article.

    Args:
        snippets: List of snippets to summarize.
    """
    if not snippets:
        st.info("エッセンスが未入力です")
        return

    st.subheader("📋 エッセンスサマリー")

    # Count by category
    category_counts = {}
    for snippet in snippets:
        cat = snippet.category
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # Display counts
    cols = st.columns(len(CATEGORY_INFO))
    for i, (category, info) in enumerate(CATEGORY_INFO.items()):
        count = category_counts.get(category, 0)
        with cols[i]:
            st.metric(
                label=f"{info['icon']} {info['label']}",
                value=count,
            )
