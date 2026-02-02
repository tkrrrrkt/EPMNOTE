"""
EPM Note Engine - Sidebar Component

Article selection and SEO keyword input.
"""

import streamlit as st

from src.config import get_tavily_domain_profiles
from src.database.models import Article, ArticleStatus
from src.ui.state import SessionState, UIPhase


# Status badge colors
STATUS_COLORS = {
    ArticleStatus.PLANNING: "🔵",
    ArticleStatus.RESEARCHING: "🟡",
    ArticleStatus.WAITING_INPUT: "🟠",
    ArticleStatus.DRAFTING: "🟣",
    ArticleStatus.REVIEW: "🟤",
    ArticleStatus.COMPLETED: "🟢",
}

STATUS_LABELS = {
    ArticleStatus.PLANNING: "企画中",
    ArticleStatus.RESEARCHING: "リサーチ中",
    ArticleStatus.WAITING_INPUT: "入力待ち",
    ArticleStatus.DRAFTING: "執筆中",
    ArticleStatus.REVIEW: "レビュー中",
    ArticleStatus.COMPLETED: "完了",
}


def render_sidebar(
    articles: list[Article],
    on_article_select: callable = None,
    on_article_update: callable = None,
    on_article_delete: callable = None,
) -> Article | None:
    """
    Render the sidebar with article selection.

    Args:
        articles: List of articles to display.
        on_article_select: Callback when an article is selected.
        on_article_update: Callback when article details are updated (article, updates_dict).
        on_article_delete: Callback when an article is deleted (article).

    Returns:
        Currently selected article or None.
    """
    with st.sidebar:
        st.title("📚 記事一覧")

        # Filter by status
        status_filter = st.selectbox(
            "ステータスで絞り込み",
            options=["すべて"] + [s.value for s in ArticleStatus],
            format_func=lambda x: x if x == "すべて" else STATUS_LABELS.get(ArticleStatus(x), x),
        )

        # Filter articles
        if status_filter != "すべて":
            filtered_articles = [a for a in articles if a.status.value == status_filter]
        else:
            filtered_articles = articles

        st.divider()

        # Article count
        st.caption(f"表示中: {len(filtered_articles)} / {len(articles)} 件")

        # Article list
        selected_article = None
        current_id = SessionState.get_current_article_id()

        # Ensure no article is selected on initial load
        # Only show selection if user has explicitly clicked an article
        if "user_selected_article" not in st.session_state:
            st.session_state["user_selected_article"] = False
            current_id = None
            SessionState.set_current_article_id(None)

        # If user hasn't explicitly selected, ensure current_id is None
        if not st.session_state.get("user_selected_article"):
            current_id = None

        # Validate current_id - reset if it doesn't match any article in filtered list
        if current_id and not any(a.id == current_id for a in filtered_articles):
            current_id = None
            SessionState.set_current_article_id(None)

        for article in filtered_articles:
            is_selected = current_id is not None and article.id == current_id
            # Show neutral badge (blue) when not selected, actual status when selected
            if is_selected:
                status_badge = STATUS_COLORS.get(article.status, "⚪")
            else:
                status_badge = "🔵"  # Neutral blue for unselected

            # Create clickable article card
            with st.container():
                col1, col2 = st.columns([1, 9])
                with col1:
                    st.write(status_badge)
                with col2:
                    # Use button for selection - only "primary" when explicitly selected
                    button_type = "primary" if is_selected else "secondary"
                    if st.button(
                        f"**{article.week_id}**\n{article.title[:25]}...",
                        key=f"article_{article.id}",
                        type=button_type,
                        use_container_width=True,
                    ):
                        # Mark that user has explicitly selected an article
                        st.session_state["user_selected_article"] = True
                        SessionState.set_current_article_id(article.id)
                        if on_article_select:
                            on_article_select(article)
                        st.rerun()

            # Show article details right below the selected article button
            if is_selected:
                selected_article = article
                render_article_details(selected_article, on_article_update, on_article_delete)
                st.divider()

        # Show prompt if no article selected
        if not selected_article:
            st.divider()
            st.info("👆 記事を選択してください")

        return selected_article


def render_article_details(
    article: Article,
    on_article_update: callable = None,
    on_article_delete: callable = None,
) -> None:
    """
    Render detailed information about the selected article.

    Args:
        article: The selected article.
        on_article_update: Callback when article details are updated.
        on_article_delete: Callback when the article is deleted.
    """
    st.subheader("📝 選択中の記事")

    # Basic info
    st.markdown(f"**{article.title}**")
    st.caption(f"Week ID: {article.week_id}")

    # Status
    status_badge = STATUS_COLORS.get(article.status, "⚪")
    status_label = STATUS_LABELS.get(article.status, article.status.value)
    st.markdown(f"ステータス: {status_badge} {status_label}")

    # Edit mode toggle
    edit_mode_key = f"edit_mode_{article.id}"
    if edit_mode_key not in st.session_state:
        st.session_state[edit_mode_key] = False

    if st.button(
        "❌ 編集を閉じる" if st.session_state[edit_mode_key] else "✏️ メタデータ編集",
        key=f"toggle_edit_{article.id}",
        use_container_width=True,
    ):
        st.session_state[edit_mode_key] = not st.session_state[edit_mode_key]
        st.rerun()

    # Edit mode
    if st.session_state[edit_mode_key]:
        render_article_edit_form(article, on_article_update)
    else:
        # View mode (original display)
        if article.target_persona:
            st.markdown(f"**ターゲット:** {article.target_persona}")

        if article.hook_statement:
            st.info(f"💬 {article.hook_statement}")

        if article.content_outline:
            with st.expander("見出し案"):
                st.write(article.content_outline)

    # SEO Keywords input (always show for easy access to re-research)
    st.divider()
    render_seo_input(article)

    # Upload status reset (only show if uploaded)
    if article.is_uploaded:
        st.divider()
        render_upload_status_section(article, on_article_update)

    # Clear article content section
    if on_article_delete:
        st.divider()
        render_clear_content_section(article, on_article_delete)


def render_upload_status_section(
    article: Article,
    on_article_update: callable = None,
) -> None:
    """
    Render upload status section with reset option.

    Args:
        article: The article to display.
        on_article_update: Callback when article is updated.
    """
    st.markdown("#### 📤 アップロード状態")
    st.success("✅ Note.comにアップロード済み")

    if article.published_url:
        st.link_button("📝 Note.comで確認", article.published_url, use_container_width=True)

    # Reset button
    if st.button(
        "🔄 アップロード済みをリセット",
        key=f"reset_upload_{article.id}",
        help="再度アップロードできるようにステータスをリセットします",
        use_container_width=True,
    ):
        if on_article_update:
            on_article_update(article, {"is_uploaded": False, "published_url": None})
            st.success("リセットしました！")
            st.rerun()


def render_clear_content_section(
    article: Article,
    on_article_clear: callable,
) -> None:
    """
    Render content clear confirmation section.

    Clears research results, draft content, review scores, etc.
    but keeps the article entry itself (title, week_id, metadata).

    Args:
        article: The article to clear.
        on_article_clear: Callback when the article content is cleared.
    """
    with st.expander("🔄 記事コンテンツをクリア", expanded=False):
        st.warning("リサーチ結果、下書き、レビュー結果などがクリアされます。")
        st.caption("※ タイトル、ターゲットペルソナ、フック、見出し案は保持されます。")

        # Confirmation checkbox
        confirm_key = f"confirm_clear_{article.id}"
        confirmed = st.checkbox(
            f"「{article.title[:20]}...」のコンテンツをクリアすることを確認",
            key=confirm_key,
        )

        if st.button(
            "🔄 クリアを実行",
            key=f"clear_{article.id}",
            type="primary" if confirmed else "secondary",
            disabled=not confirmed,
            use_container_width=True,
        ):
            on_article_clear(article)
            st.success(f"「{article.title[:20]}...」のコンテンツをクリアしました")
            st.rerun()


def render_article_edit_form(
    article: Article,
    on_article_update: callable = None,
) -> None:
    """
    Render edit form for article metadata.

    Args:
        article: The article to edit.
        on_article_update: Callback when article details are updated.
    """
    with st.form(key=f"edit_form_{article.id}"):
        st.markdown("#### 記事メタデータ編集")

        # Target persona
        new_target_persona = st.text_input(
            "ターゲットペルソナ",
            value=article.target_persona or "",
            placeholder="例: CFO, 経営企画",
            help="この記事の想定読者",
        )

        # Hook statement
        new_hook_statement = st.text_area(
            "フック（会議の一言）",
            value=article.hook_statement or "",
            placeholder="例: 「正の数字」を、誰が・いつ・どこで決めてる？",
            help="読者の注意を引く一言",
            height=80,
        )

        # Content outline
        new_content_outline = st.text_area(
            "見出し案",
            value=article.content_outline or "",
            placeholder="例: SSOTの誤解 → 3レイヤ → 成果物一覧 → 90日ロードマップ → 失敗例",
            help="記事の構成案（→で区切る）",
            height=100,
        )

        col_save, col_cancel = st.columns(2)
        with col_save:
            submitted = st.form_submit_button(
                "💾 保存",
                type="primary",
                use_container_width=True,
            )
        with col_cancel:
            cancelled = st.form_submit_button(
                "キャンセル",
                use_container_width=True,
            )

        if submitted:
            updates = {}
            if new_target_persona != (article.target_persona or ""):
                updates["target_persona"] = new_target_persona
            if new_hook_statement != (article.hook_statement or ""):
                updates["hook_statement"] = new_hook_statement
            if new_content_outline != (article.content_outline or ""):
                updates["content_outline"] = new_content_outline

            if updates and on_article_update:
                on_article_update(article, updates)
                st.session_state[f"edit_mode_{article.id}"] = False
                st.session_state["article_updated"] = True
                # Don't rerun here - let the natural flow handle it
                st.success("保存しました！")
            elif not updates:
                st.info("変更がありません")

        if cancelled:
            st.session_state[f"edit_mode_{article.id}"] = False


def render_seo_input(article: Article) -> None:
    """
    Render SEO keyword input form.

    Args:
        article: The article to set keywords for.
    """
    st.subheader("🔍 SEOキーワード設定")

    with st.form(key=f"seo_form_{article.id}"):
        profiles = get_tavily_domain_profiles()
        profile_labels = {
            "balanced": "バランス型（おすすめ）",
            "evidence": "根拠重視（官公庁・学術中心）",
            "market": "市場・競合重視（比較/ベンダー寄り）",
        }
        profile_descriptions = {
            "balanced": "信頼性と幅のバランスを取った設定です。",
            "evidence": "官公庁・学術・専門団体を優先し、根拠重視の情報を集めます。",
            "market": "比較サイト・ベンダー公式を広く拾い、市場/競合の理解を深めます。",
        }
        default_profile = st.session_state.get("tavily_profile", "balanced")
        if default_profile not in profiles:
            default_profile = "balanced"
        profile_keys = list(profiles.keys())
        selected_profile = st.selectbox(
            "リサーチモード",
            options=profile_keys,
            index=profile_keys.index(default_profile),
            format_func=lambda key: profile_labels.get(key, key),
            help="Tavilyの検索対象ドメインの方針を選びます。",
            key="tavily_profile",
        )
        st.caption(profile_descriptions.get(selected_profile, ""))

        seo_keywords = st.text_input(
            "SEOキーワード",
            value=article.seo_keywords or "",
            placeholder="例: 予実管理, 数字が合わない, 経営管理",
            help="カンマ区切りで複数入力可能",
        )

        submitted = st.form_submit_button(
            "リサーチ開始 🔍",
            type="primary",
            use_container_width=True,
        )

        if submitted and seo_keywords:
            # Store in session state for processing
            st.session_state["pending_seo_keywords"] = seo_keywords
            st.session_state["pending_tavily_profile"] = selected_profile
            st.session_state["pending_article_id"] = article.id
            SessionState.set_ui_phase(UIPhase.RESEARCH)
            st.rerun()


def render_status_summary(articles: list[Article]) -> None:
    """
    Render a summary of articles by status.

    Args:
        articles: List of all articles.
    """
    st.sidebar.divider()
    st.sidebar.subheader("📊 進捗サマリー")

    # Count by status
    status_counts = {}
    for article in articles:
        status = article.status
        status_counts[status] = status_counts.get(status, 0) + 1

    # Display counts
    for status in ArticleStatus:
        count = status_counts.get(status, 0)
        badge = STATUS_COLORS.get(status, "⚪")
        label = STATUS_LABELS.get(status, status.value)
        st.sidebar.caption(f"{badge} {label}: {count}")
