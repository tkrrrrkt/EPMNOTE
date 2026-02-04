"""
EPM Note Engine - Main Streamlit Application

Entry point for the article generation system.
"""

import re

import streamlit as st

from src.config import get_settings


def sort_articles_by_week_id(articles: list) -> list:
    """
    Sort articles by week_id using natural sort order.

    Week IDs like "Week1-1", "Week2-1", "Week10-1" are sorted correctly
    as 1, 2, 10 instead of lexicographic order 1, 10, 2.
    """
    def extract_week_numbers(article):
        match = re.match(r"Week(\d+)-(\d+)", article.week_id or "")
        if match:
            return (int(match.group(1)), int(match.group(2)))
        return (999, 999)  # Put invalid week_ids at the end

    return sorted(articles, key=extract_week_numbers)
from src.database.connection import get_session, init_db
from src.database.models import Article, ArticleStatus
from src.repositories.article_repository import ArticleRepository
from src.repositories.snippet_repository import SnippetRepository
from src.ui.state import SessionState, UIPhase, get_phase_display_info
from src.ui.components import (
    render_sidebar,
    render_input_form,
    render_editor,
    render_progress_indicator,
)
from src.ui.components.progress import render_phase_header, render_compact_progress
from src.ui.components.admin import render_admin_panel
from src.ui.components.help_page import render_help_page
from src.automation.note_uploader import NoteUploader, UploadResult


# Page configuration
st.set_page_config(
    page_title="EPM Note Engine",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main():
    """Main application entry point."""
    # Initialize session state
    SessionState.initialize()

    # Check for admin mode
    if st.session_state.get("admin_mode"):
        render_admin_mode()
        return

    # Check for help mode
    if st.session_state.get("show_help"):
        render_help_mode()
        return

    # Initialize database (create tables if not exist)
    try:
        init_db()
    except Exception as e:
        st.error(f"データベース接続エラー: {e}")
        st.info("Docker Composeが起動していることを確認してください: `docker-compose up -d`")
        return

    # Get current phase
    current_phase = SessionState.get_ui_phase()

    # Header
    st.title("📝 EPM Note Engine")
    st.caption("経営管理のプロが書いたようなNote記事を半自動生成")

    # Main content area
    with get_session() as session:
        article_repo = ArticleRepository(session)
        snippet_repo = SnippetRepository(session)

        # Load all articles with natural sort by week_id
        articles = sort_articles_by_week_id(list(article_repo.get_all()))

        # Define article update handler
        def handle_article_update(article: Article, updates: dict) -> None:
            """Handle article metadata updates from sidebar."""
            for key, value in updates.items():
                setattr(article, key, value)
            article_repo.update(article)
            # Explicit commit to ensure changes persist before potential rerun
            session.commit()

        # Define article content clear handler
        def handle_article_clear(article: Article) -> None:
            """Handle article content clearing from sidebar.

            Clears research results, drafts, reviews, etc.
            but preserves title, week_id, and metadata (persona, hook, outline).
            """
            # Clear content-related fields
            article.seo_keywords = None
            article.competitor_analysis = None
            article.research_summary = None
            article.outline_json = None
            article.draft_content_md = None
            article.final_content_md = None
            article.title_candidates = None
            article.image_prompts = None
            article.sns_posts = None
            article.review_score = None
            article.review_feedback = None
            article.is_uploaded = False
            article.published_url = None
            article.status = ArticleStatus.PLANNING
            article_repo.update(article)
            # Explicit commit to ensure changes persist before rerun
            session.commit()

        # Render sidebar and get selected article
        selected_article = render_sidebar(
            articles,
            on_article_select=lambda a: handle_article_select(a),
            on_article_update=handle_article_update,
            on_article_delete=handle_article_clear,  # Clear content, not delete
        )

        # Progress indicator with article data for completion status
        render_progress_indicator(current_phase, clickable=True, article=selected_article)
        st.divider()

        # Main content based on phase
        if current_phase == UIPhase.ARTICLE_SELECT:
            render_article_select_phase(selected_article)

        elif current_phase == UIPhase.RESEARCH:
            render_research_phase(selected_article, article_repo)

        elif current_phase == UIPhase.ESSENCE_INPUT:
            if selected_article:
                snippets = list(snippet_repo.get_by_article_id(selected_article.id))
                render_essence_input_phase(selected_article, snippets, snippet_repo)
            else:
                st.warning("記事を選択してください")
                SessionState.set_ui_phase(UIPhase.ARTICLE_SELECT)

        elif current_phase == UIPhase.DRAFTING:
            render_drafting_phase(selected_article, article_repo)

        elif current_phase == UIPhase.REVIEW:
            render_review_phase(selected_article, article_repo)

        elif current_phase == UIPhase.EDITOR:
            if selected_article:
                render_editor_phase(selected_article, article_repo)
            else:
                st.warning("記事を選択してください")
                SessionState.set_ui_phase(UIPhase.ARTICLE_SELECT)

        elif current_phase == UIPhase.UPLOAD:
            render_upload_phase(selected_article, article_repo)

    # Display any pending messages
    display_messages()

    # Add admin toggle to sidebar
    render_admin_toggle()


def handle_article_select(article: Article) -> None:
    """Handle article selection event."""
    SessionState.set_current_article_id(article.id)
    SessionState.sync_from_article_status(article.status)


def render_article_select_phase(article: Article | None) -> None:
    """Render the article selection phase."""
    render_phase_header(UIPhase.ARTICLE_SELECT)

    if article:
        st.info(f"選択中: **{article.title}**")
        st.markdown("サイドバーでSEOキーワードを入力して「リサーチ開始」をクリックしてください。")
    else:
        st.markdown("""
        ### 使い方

        1. **記事を選択**: サイドバーから記事候補を選択
        2. **SEOキーワード設定**: ターゲットキーワードを入力
        3. **リサーチ開始**: 競合分析を実行
        4. **エッセンス入力**: 失敗談や意見を入力
        5. **AI生成**: 記事を自動生成
        6. **レビュー**: 品質チェックと修正
        7. **投稿**: Note.comへ下書き保存
        """)

        # Quick stats
        st.divider()
        col1, col2, col3 = st.columns(3)

        with get_session() as session:
            repo = ArticleRepository(session)
            counts = repo.count_by_status()

            with col1:
                st.metric("企画中", counts.get(ArticleStatus.PLANNING, 0))
            with col2:
                st.metric("作成中", sum([
                    counts.get(ArticleStatus.RESEARCHING, 0),
                    counts.get(ArticleStatus.WAITING_INPUT, 0),
                    counts.get(ArticleStatus.DRAFTING, 0),
                    counts.get(ArticleStatus.REVIEW, 0),
                ]))
            with col3:
                st.metric("完了", counts.get(ArticleStatus.COMPLETED, 0))


def render_research_phase(article: Article | None, repo: ArticleRepository) -> None:
    """Render the research phase."""
    render_phase_header(UIPhase.RESEARCH)

    if not article:
        st.warning("記事が選択されていません")
        SessionState.set_ui_phase(UIPhase.ARTICLE_SELECT)
        return

    # Check for pending SEO keywords (new research to run)
    pending_keywords = st.session_state.get("pending_seo_keywords")
    pending_article_id = st.session_state.get("pending_article_id")

    # Check if research already completed (article has research_summary)
    if article.research_summary and article.seo_keywords:
        # Research already done - show results and proceed button
        st.success("リサーチ完了！")
        st.info(f"SEOキーワード: **{article.seo_keywords}**")
        st.markdown(article.research_summary)

        # Show competitor analysis if available
        if article.competitor_analysis:
            with st.expander("🔍 競合分析詳細", expanded=False):
                urls = article.competitor_analysis.get("urls", [])
                gaps = article.competitor_analysis.get("content_gaps", [])
                if urls:
                    st.markdown("**競合URL:**")
                    for url in urls[:5]:
                        st.markdown(f"- {url}")
                if gaps:
                    st.markdown("**コンテンツギャップ:**")
                    for gap in gaps:
                        st.markdown(f"- {gap}")

        if st.button("エッセンス入力へ進む", type="primary"):
            SessionState.set_ui_phase(UIPhase.ESSENCE_INPUT)
            st.rerun()

    elif pending_keywords and pending_article_id == article.id:
        # Run new research via WorkflowService
        st.info(f"SEOキーワード: **{pending_keywords}**")
        pending_profile = st.session_state.get("pending_tavily_profile", "balanced")
        profile_labels = {
            "balanced": "バランス型",
            "evidence": "根拠重視",
            "market": "市場・競合重視",
        }
        st.caption(f"リサーチモード: {profile_labels.get(pending_profile, pending_profile)}")

        # Progress indicators
        progress_placeholder = st.empty()
        status_placeholder = st.empty()

        try:
            from src.workflow.service import WorkflowService

            def on_progress(percent: int, message: str) -> None:
                progress_placeholder.progress(percent / 100, text=message)
                status_placeholder.markdown(f"🔍 {message}")

            with st.spinner("リサーチを実行中..."):
                service = WorkflowService()
                state = service.run_research_only(
                    article_id=str(article.id),
                    seo_keywords=pending_keywords,
                    on_progress=on_progress,
                    tavily_profile=pending_profile,
                )

            # Clear pending state
            del st.session_state["pending_seo_keywords"]
            if "pending_tavily_profile" in st.session_state:
                del st.session_state["pending_tavily_profile"]
            del st.session_state["pending_article_id"]

            # Show success summary
            st.success("リサーチ完了！")
            st.markdown(state["research_summary"])

            if st.button("エッセンス入力へ進む", type="primary"):
                SessionState.set_ui_phase(UIPhase.ESSENCE_INPUT)
                st.rerun()

        except Exception as e:
            st.error(f"リサーチに失敗しました: {e}")
            import traceback
            st.code(traceback.format_exc())
            if st.button("再試行"):
                st.rerun()
    else:
        st.warning("SEOキーワードが設定されていません")
        if st.button("記事選択に戻る"):
            SessionState.set_ui_phase(UIPhase.ARTICLE_SELECT)
            st.rerun()


def render_essence_input_phase(
    article: Article,
    snippets: list,
    snippet_repo: SnippetRepository,
) -> None:
    """Render the essence input phase."""

    def on_submit(new_snippets):
        # Save new snippets
        from src.database.models import Snippet
        for snippet_data in new_snippets:
            snippet = Snippet(
                article_id=article.id,
                category=snippet_data["category"],
                content=snippet_data["content"],
                tags=snippet_data.get("tags"),
            )
            snippet_repo.create(snippet)

    render_input_form(
        article=article,
        existing_snippets=snippets,
        on_submit=on_submit,
        on_skip=lambda: None,
    )


def render_drafting_phase(article: Article | None, repo: ArticleRepository) -> None:
    """Render the drafting phase with integrated review and Self-Correction."""
    render_phase_header(UIPhase.DRAFTING)

    if not article:
        st.warning("記事が選択されていません")
        SessionState.set_ui_phase(UIPhase.ARTICLE_SELECT)
        return

    st.info(f"記事: **{article.title}**")

    # Check if already completed (has review score)
    if article.review_score and article.review_score > 0:
        st.success(f"記事生成・レビュー完了！ スコア: **{article.review_score}点**")
        st.markdown(f"**文字数:** {len(article.draft_content_md or '')} 文字")

        if article.review_feedback:
            with st.expander("📋 レビューフィードバック", expanded=False):
                st.markdown(article.review_feedback)

        if st.button("エディタへ進む", type="primary"):
            SessionState.set_ui_phase(UIPhase.EDITOR)
            st.rerun()
        return

    # Check if draft exists but not reviewed yet
    if article.draft_content_md and article.status == ArticleStatus.REVIEW:
        st.info("レビュー待ちの下書きがあります")
        with st.expander("生成された記事をプレビュー", expanded=False):
            content = article.draft_content_md
            st.markdown(content[:2000] + "..." if len(content) > 2000 else content)

        if st.button("レビューを実行", type="primary"):
            st.session_state["generation_started"] = True
            st.rerun()

    # Check if we should start generation
    if not st.session_state.get("generation_started"):
        st.markdown("""
        ### 記事生成の準備ができました

        AIが以下の処理を**一括実行**します：
        - 📝 リサーチ結果を分析して記事を生成
        - ✨ エッセンスを記事に反映
        - 🎯 タイトル候補・SNS投稿文を生成
        - 📊 品質レビュー（80点未満なら自動修正）
        """)

        if st.button("記事を生成する", type="primary"):
            st.session_state["generation_started"] = True
            st.rerun()
        return

    # Run generation with review via WorkflowService
    progress_placeholder = st.empty()
    status_placeholder = st.empty()
    result_placeholder = st.empty()

    try:
        from src.workflow.service import WorkflowService

        def on_progress(percent: int, message: str) -> None:
            progress_placeholder.progress(percent / 100, text=message)
            status_placeholder.markdown(f"⚙️ {message}")

        with st.spinner("記事生成・レビューを実行中..."):
            service = WorkflowService()
            state = service.run_generation_with_review(
                article_id=str(article.id),
                on_progress=on_progress,
            )

        # Clear session state
        if "generation_started" in st.session_state:
            del st.session_state["generation_started"]

        # Show result
        score = state["review_score"]
        if score >= 80:
            result_placeholder.success(f"レビュー合格！ スコア: **{score}点**")
        else:
            result_placeholder.warning(f"スコア: **{score}点** (修正後)")

        st.markdown(f"**文字数:** {len(state['draft_content_md'])} 文字")

        if state["review_feedback"]:
            with st.expander("📋 レビューフィードバック", expanded=False):
                st.markdown(state["review_feedback"])

        if st.button("エディタへ進む", type="primary"):
            SessionState.set_ui_phase(UIPhase.EDITOR)
            st.rerun()

    except Exception as e:
        st.error(f"記事生成に失敗しました: {e}")
        import traceback
        st.code(traceback.format_exc())
        if "generation_started" in st.session_state:
            del st.session_state["generation_started"]
        if st.button("再試行"):
            st.session_state["generation_started"] = True
            st.rerun()


def render_review_phase(article: Article | None, repo: ArticleRepository) -> None:
    """Render the review phase (shows results, generation is done in drafting phase)."""
    render_phase_header(UIPhase.REVIEW)

    if not article:
        st.warning("記事が選択されていません")
        SessionState.set_ui_phase(UIPhase.ARTICLE_SELECT)
        return

    st.info(f"記事: **{article.title}**")

    # Check if review is already done
    if article.review_score and article.review_score > 0:
        # Show review results
        if article.review_score >= 80:
            st.success(f"レビュー合格: **{article.review_score}点**")
        else:
            st.warning(f"レビュースコア: **{article.review_score}点**")

        if article.review_feedback:
            with st.expander("📋 レビューフィードバック", expanded=True):
                st.markdown(article.review_feedback)

        st.markdown(f"**文字数:** {len(article.draft_content_md or '')} 文字")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 再生成（リサーチから）"):
                # Reset to allow regeneration
                article.review_score = 0
                article.draft_content_md = None
                article.status = ArticleStatus.WAITING_INPUT
                repo.update(article)
                SessionState.set_ui_phase(UIPhase.ESSENCE_INPUT)
                st.rerun()
        with col2:
            if st.button("エディタへ進む", type="primary"):
                SessionState.set_ui_phase(UIPhase.EDITOR)
                st.rerun()
        return

    # If no review yet, redirect to drafting (which now includes review)
    if not article.draft_content_md:
        st.info("記事がまだ生成されていません。生成フェーズに移動します。")
        if st.button("記事生成へ", type="primary"):
            SessionState.set_ui_phase(UIPhase.DRAFTING)
            st.rerun()
        return

    # Draft exists but no review - this shouldn't happen with new flow
    # but handle for backward compatibility
    st.info("記事は生成済みですが、レビューが完了していません。")
    st.markdown("記事生成フェーズで統合レビューを実行してください。")

    if st.button("記事生成・レビューへ", type="primary"):
        SessionState.set_ui_phase(UIPhase.DRAFTING)
        st.rerun()


def render_editor_phase(article: Article, repo: ArticleRepository) -> None:
    """Render the editor phase."""

    def on_save(edited_content):
        article.final_content_md = edited_content.get("content", article.final_content_md)
        if edited_content.get("title"):
            article.title = edited_content["title"]
        if edited_content.get("sns_x") or edited_content.get("sns_linkedin"):
            article.sns_posts = {
                "x": edited_content.get("sns_x", ""),
                "linkedin": edited_content.get("sns_linkedin", ""),
            }
        repo.update(article)

    def on_upload(edited_content):
        on_save(edited_content)
        SessionState.set_ui_phase(UIPhase.UPLOAD)

    render_editor(
        article=article,
        on_save=on_save,
        on_upload=on_upload,
    )


def render_upload_phase(article: Article | None, repo: ArticleRepository) -> None:
    """Render the upload phase."""
    render_phase_header(UIPhase.UPLOAD)

    if not article:
        st.warning("記事が選択されていません")
        SessionState.set_ui_phase(UIPhase.ARTICLE_SELECT)
        return

    st.info(f"記事: **{article.title}**")

    # 認証情報チェック
    settings = get_settings()
    if not settings.note_email or not settings.note_password:
        st.error("Note.comの認証情報が設定されていません。")
        st.code("NOTE_EMAIL=your-email@example.com\nNOTE_PASSWORD=your-password", language="bash")
        st.info(".envファイルに上記を追加してください。")
        if st.button("🔙 戻る"):
            SessionState.set_ui_phase(UIPhase.EDITOR)
            st.rerun()
        return

    # 最終コンテンツ確認
    content = article.final_content_md or article.draft_content_md
    if not content:
        st.error("アップロードするコンテンツがありません。")
        if st.button("🔙 エディタに戻る"):
            SessionState.set_ui_phase(UIPhase.EDITOR)
            st.rerun()
        return

    # アップロード済みの場合
    if article.is_uploaded:
        st.success("この記事は既にNote.comにアップロード済みです。")
        col1, col2 = st.columns(2)
        with col1:
            force_reupload = st.button("🔄 再アップロード", use_container_width=True)
        with col2:
            st.link_button(
                "📝 Note.comを開く",
                article.published_url or "https://note.com/",
                use_container_width=True,
            )

        if not force_reupload:
            return

        # Reset upload state and proceed with normal upload flow
        article.is_uploaded = False
        article.published_url = None
        repo.update(article)
        st.info("再アップロードを開始します。")

    # コンテンツ表示
    st.markdown("### Note.comに下書きとして保存")
    st.markdown(f"**タイトル:** {article.title}")
    st.markdown(f"**文字数:** {len(content)}文字")

    # 方法1: クリップボードにコピー（推奨）
    st.markdown("#### 方法1: 手動コピー（推奨）")
    st.info("下のテキストエリアから内容をコピーして、Note.comに貼り付けてください。")

    col1, col2 = st.columns(2)
    with col1:
        # タイトルをコピー
        st.text_input("タイトル（コピー用）", value=article.title, key="copy_title")
    with col2:
        # ラベル分の高さを揃えるためのスペーサー
        st.markdown('<p style="font-size: 14px; margin-bottom: 4px;">&nbsp;</p>', unsafe_allow_html=True)
        st.link_button("📝 Note.comで新規投稿", "https://note.com/new", use_container_width=True)

    # コンテンツをテキストエリアで表示（コピー可能）
    st.text_area("本文（コピー用）", value=content, height=300, key="copy_content")
    st.caption("上のテキストエリアから内容をコピーして、Note.comに貼り付けてください。")

    # 完了ボタン
    if st.button("✅ Note.comへの投稿完了", type="primary", use_container_width=True):
        article.is_uploaded = True
        repo.update(article)
        st.success("投稿完了としてマークしました！")
        st.balloons()

    st.divider()

    # 方法2: 自動アップロード
    with st.expander("方法2: 自動アップロード", expanded=False):

        if st.button("📤 自動アップロードを試す", use_container_width=True):
            progress_placeholder = st.empty()
            status_placeholder = st.empty()

            with progress_placeholder:
                with st.spinner("Note.comに接続中..."):
                    try:
                        uploader = NoteUploader(headless=True)
                        result = uploader.upload_draft(
                            title=article.title,
                            content_md=content,
                        )

                        if result.success:
                            article.is_uploaded = True
                            article.published_url = result.draft_url or article.published_url
                            repo.update(article)

                            status_placeholder.success("Note.comへの下書き保存が完了しました！")
                            st.balloons()

                            if result.draft_url:
                                st.link_button("📝 Note.comで確認", result.draft_url, use_container_width=True)
                            else:
                                st.link_button("📝 Note.comを開く", "https://note.com/", use_container_width=True)
                        else:
                            status_placeholder.error(f"アップロードに失敗しました: {result.error_message}")
                            if result.screenshot_path:
                                st.image(result.screenshot_path, caption="エラー時のスクリーンショット")
                            if result.stderr:
                                with st.expander("Playwrightログ（stderr）"):
                                    st.code(result.stderr)

                    except ValueError as e:
                        status_placeholder.error(f"設定エラー: {e}")
                    except Exception as e:
                        import traceback
                        status_placeholder.error(f"予期しないエラー: {e}")
                        st.code(traceback.format_exc())

    # ナビゲーションボタン
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔙 エディタに戻る", use_container_width=True):
            SessionState.set_ui_phase(UIPhase.EDITOR)
            st.rerun()
    with col2:
        if st.button("📋 記事一覧に戻る", use_container_width=True):
            SessionState.set_ui_phase(UIPhase.ARTICLE_SELECT)
            st.rerun()


def display_messages() -> None:
    """Display any pending messages."""
    messages = SessionState.get_messages()
    for msg in messages:
        if msg["type"] == "success":
            st.success(msg["text"])
        elif msg["type"] == "error":
            st.error(msg["text"])
        elif msg["type"] == "warning":
            st.warning(msg["text"])
        else:
            st.info(msg["text"])
    SessionState.clear_messages()


def render_admin_mode() -> None:
    """Render admin mode interface."""
    st.title("⚙️ EPM Note Engine - 管理パネル")

    # Back button in sidebar
    with st.sidebar:
        if st.button("← 記事作成に戻る", use_container_width=True):
            st.session_state.admin_mode = False
            st.rerun()

        st.divider()
        st.caption("管理機能")

    # Render admin panel
    render_admin_panel()


def render_help_mode() -> None:
    """Render help mode interface."""
    # Back button in sidebar
    with st.sidebar:
        if st.button("← 記事作成に戻る", use_container_width=True):
            st.session_state.show_help = False
            st.rerun()

        st.divider()
        st.caption("ヘルプページ")

    # Render help page
    render_help_page()


# Add admin toggle to sidebar (called from main)
def render_admin_toggle() -> None:
    """Render admin mode toggle in sidebar."""
    with st.sidebar:
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            with st.expander("⚙️ 管理機能"):
                if st.button("管理パネルを開く", use_container_width=True):
                    st.session_state.admin_mode = True
                    st.rerun()
        with col2:
            with st.expander("❓ ヘルプ"):
                if st.button("使い方を見る", use_container_width=True):
                    st.session_state.show_help = True
                    st.rerun()


if __name__ == "__main__":
    main()
