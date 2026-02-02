"""
EPM Note Engine - Editor Component

Article editing and final review before publishing.
"""

import streamlit as st

from src.database.models import Article
from src.ui.state import SessionState, UIPhase


def render_editor(
    article: Article,
    on_save: callable = None,
    on_upload: callable = None,
) -> dict | None:
    """
    Render the article editor.

    Args:
        article: The article to edit.
        on_save: Callback when article is saved.
        on_upload: Callback when upload is requested.

    Returns:
        Dictionary with edited content or None.
    """
    st.header("📝 記事エディタ")

    # Review score display
    if article.review_score:
        col1, col2, col3 = st.columns(3)
        with col1:
            score_color = "green" if article.review_score >= 80 else "orange"
            st.metric("レビュースコア", f"{article.review_score}/100")
        with col2:
            st.metric("ステータス", "✅ 合格" if article.review_score >= 80 else "⚠️ 要改善")

    if article.review_feedback:
        with st.expander("📋 レビューフィードバック", expanded=False):
            st.markdown(article.review_feedback)

    st.divider()

    # Tabs for different editing sections
    tab1, tab2, tab3, tab4 = st.tabs(["📄 本文", "📌 タイトル", "📱 SNS投稿", "🎨 画像プロンプト"])

    edited_content = {}

    # Tab 1: Main content editor
    with tab1:
        st.subheader("記事本文（Markdown）")

        content = st.text_area(
            "本文を編集",
            value=article.final_content_md or article.draft_content_md or "",
            height=500,
            key="editor_content",
            help="Markdown形式で記述。見出しは ## で、リストは - で記述できます。",
        )
        edited_content["content"] = content

        # Word count
        word_count = len(content) if content else 0
        target_min, target_max = 3000, 4500
        if word_count < target_min:
            st.warning(f"文字数: {word_count} / 目標: {target_min}-{target_max}文字（不足）")
        elif word_count > target_max:
            st.warning(f"文字数: {word_count} / 目標: {target_min}-{target_max}文字（超過）")
        else:
            st.success(f"文字数: {word_count} / 目標: {target_min}-{target_max}文字（OK）")

        # Preview toggle
        if st.checkbox("プレビュー表示"):
            st.divider()
            st.markdown("### プレビュー")
            st.markdown(content)

    # Tab 2: Title selection
    with tab2:
        st.subheader("タイトル選択")

        title_candidates = article.title_candidates or []
        if isinstance(title_candidates, dict):
            title_candidates = title_candidates.get("titles", [])

        if title_candidates:
            selected_title = st.radio(
                "タイトル候補から選択",
                options=title_candidates,
                index=0,
                key="selected_title",
            )
            edited_content["title"] = selected_title
        else:
            # Manual title input
            selected_title = st.text_input(
                "タイトル",
                value=article.title,
                key="manual_title",
            )
            edited_content["title"] = selected_title

        st.caption("※ 選択したタイトルがNote.comに投稿されます")

    # Tab 3: SNS posts
    with tab3:
        st.subheader("SNS投稿文案")

        sns_posts = article.sns_posts or {}
        if isinstance(sns_posts, str):
            sns_posts = {"x": sns_posts, "linkedin": ""}

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**X (Twitter)**")
            x_post = st.text_area(
                "X投稿文（140文字以内）",
                value=sns_posts.get("x", ""),
                height=150,
                max_chars=280,
                key="x_post",
            )
            char_count = len(x_post)
            if char_count > 140:
                st.warning(f"{char_count}/140文字（超過）")
            else:
                st.caption(f"{char_count}/140文字")
            edited_content["sns_x"] = x_post

            if st.button("📋 コピー", key="copy_x"):
                st.code(x_post)

        with col2:
            st.markdown("**LinkedIn**")
            linkedin_post = st.text_area(
                "LinkedIn投稿文（300文字程度）",
                value=sns_posts.get("linkedin", ""),
                height=150,
                key="linkedin_post",
            )
            st.caption(f"{len(linkedin_post)}文字")
            edited_content["sns_linkedin"] = linkedin_post

            if st.button("📋 コピー", key="copy_linkedin"):
                st.code(linkedin_post)

    # Tab 4: Image prompts
    with tab4:
        st.subheader("画像生成プロンプト")
        st.caption("図解生成用のプロンプトです。画像生成AIに入力してください。")

        image_prompts = article.image_prompts or []
        if isinstance(image_prompts, dict):
            image_prompts = image_prompts.get("prompts", [])

        if image_prompts:
            for i, prompt in enumerate(image_prompts, 1):
                with st.expander(f"プロンプト {i}", expanded=i == 1):
                    st.code(prompt, language=None)
                    if st.button(f"📋 コピー", key=f"copy_prompt_{i}"):
                        st.success("コピーしました！")
        else:
            st.info("画像プロンプトは生成されていません")

    st.divider()

    # Action buttons
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("💾 保存", type="primary", use_container_width=True):
            if on_save:
                on_save(edited_content)
            st.success("保存しました！")

    with col2:
        # Check if ready for upload
        is_ready = article.review_score and article.review_score >= 80
        if st.button(
            "🚀 Noteへ下書き保存",
            type="primary" if is_ready else "secondary",
            use_container_width=True,
            disabled=not is_ready,
        ):
            if on_upload:
                on_upload(edited_content)
            SessionState.set_ui_phase(UIPhase.UPLOAD)
            st.rerun()

        if not is_ready:
            st.caption("レビュースコア80点以上で有効")

    with col3:
        if st.button("🔄 再生成", use_container_width=True):
            SessionState.set_ui_phase(UIPhase.DRAFTING)
            st.rerun()

    with col4:
        if st.button("🔙 戻る", use_container_width=True):
            SessionState.set_ui_phase(UIPhase.ARTICLE_SELECT)
            st.rerun()

    return edited_content


def render_upload_progress() -> None:
    """Render the upload progress indicator."""
    st.header("🚀 Note.comへアップロード中")

    with st.spinner("ブラウザを起動しています..."):
        progress_bar = st.progress(0)

        # Simulated progress steps
        steps = [
            (10, "ブラウザ起動中..."),
            (30, "Note.comにログイン中..."),
            (50, "新規投稿画面を開いています..."),
            (70, "タイトルと本文を入力中..."),
            (90, "下書き保存中..."),
            (100, "完了！"),
        ]

        # Note: In actual implementation, this would be updated
        # by the Playwright automation process
        st.info("Playwrightによる自動化処理を実行中...")


def render_upload_result(success: bool, error_message: str = None) -> None:
    """
    Render the upload result.

    Args:
        success: Whether the upload was successful.
        error_message: Error message if failed.
    """
    if success:
        st.success("✅ Note.comへの下書き保存が完了しました！")
        st.balloons()

        col1, col2 = st.columns(2)
        with col1:
            if st.button("📝 Note.comで確認", use_container_width=True):
                st.markdown("[Note.comを開く](https://note.com/)", unsafe_allow_html=True)
        with col2:
            if st.button("🔙 記事一覧に戻る", use_container_width=True):
                SessionState.set_ui_phase(UIPhase.ARTICLE_SELECT)
                st.rerun()
    else:
        st.error(f"❌ アップロードに失敗しました: {error_message}")

        if st.button("🔄 リトライ", type="primary"):
            SessionState.set_ui_phase(UIPhase.UPLOAD)
            st.rerun()

        if st.button("🔙 エディタに戻る"):
            SessionState.set_ui_phase(UIPhase.EDITOR)
            st.rerun()
