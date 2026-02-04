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
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📄 本文", "📌 タイトル", "📱 SNS投稿", "🖼️ 画像", "📊 SEO分析"
    ])

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

    # Tab 4: Images (prompts + searched images)
    with tab4:
        st.subheader("🖼️ 画像挿入支援")

        # Section 1: Image search results from Unsplash/Pexels
        image_suggestions = article.image_suggestions or []
        if isinstance(image_suggestions, dict):
            image_suggestions = image_suggestions.get("results", [])

        if image_suggestions:
            st.markdown("### 📷 おすすめ画像（Unsplash/Pexels）")
            st.caption("クリックで画像URLをコピー。記事に挿入してください。")

            for i, suggestion in enumerate(image_suggestions):
                query = suggestion.get("query", f"画像 {i+1}")
                images = suggestion.get("images", [])
                source = suggestion.get("source", "")

                if images:
                    with st.expander(f"🔍 「{query}」の検索結果 ({source})", expanded=i == 0):
                        cols = st.columns(min(len(images), 3))
                        for j, img in enumerate(images[:3]):
                            with cols[j]:
                                # Display image thumbnail
                                st.image(
                                    img.get("url_small", ""),
                                    caption=f"📸 {img.get('author', 'Unknown')}",
                                    use_container_width=True,
                                )
                                # Copy buttons for different sizes
                                url_regular = img.get("url_regular", "")
                                if url_regular:
                                    st.code(url_regular, language=None)
                                    st.caption(f"Alt: {img.get('alt_text', '')[:50]}...")
        else:
            st.info("💡 画像APIを設定すると、おすすめ画像が表示されます")
            st.caption("UNSPLASH_ACCESS_KEY または PEXELS_API_KEY を .env に設定してください")

        st.divider()

        # Section 2: Image generation prompts
        st.markdown("### 🎨 図解生成プロンプト")
        st.caption("画像生成AIに入力してください（DALL-E, Midjourney等）")

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

    # Tab 5: SEO Keyword Analysis
    with tab5:
        st.subheader("📊 SEOキーワード分析")

        keyword_analysis = article.keyword_analysis or {}
        if isinstance(keyword_analysis, str):
            keyword_analysis = {}

        if keyword_analysis:
            # Overall SEO score
            overall_score = keyword_analysis.get("overall_seo_score", 0)
            density_score = keyword_analysis.get("keyword_density_score", 0)
            placement_score = keyword_analysis.get("placement_score", 0)

            # Score display
            col1, col2, col3 = st.columns(3)
            with col1:
                score_color = "🟢" if overall_score >= 70 else "🟡" if overall_score >= 50 else "🔴"
                st.metric(f"{score_color} 総合SEOスコア", f"{overall_score:.0f}/100")
            with col2:
                st.metric("📈 キーワード密度", f"{density_score:.0f}/100")
            with col3:
                st.metric("📍 配置スコア", f"{placement_score:.0f}/100")

            st.divider()

            # Primary keyword details
            primary_kw = keyword_analysis.get("primary_keyword")
            if primary_kw:
                st.markdown("### 🎯 主要キーワード分析")
                kw_col1, kw_col2, kw_col3 = st.columns(3)
                with kw_col1:
                    st.metric("キーワード", primary_kw.get("keyword", ""))
                with kw_col2:
                    st.metric("出現回数", primary_kw.get("count", 0))
                with kw_col3:
                    density = primary_kw.get("density", 0)
                    st.metric("密度", f"{density:.2f}%")

                # Position analysis
                positions = primary_kw.get("positions", [])
                if positions:
                    st.markdown("**配置位置:**")
                    pos_cols = st.columns(len(positions) if len(positions) <= 5 else 5)
                    for idx, pos in enumerate(positions[:5]):
                        with pos_cols[idx]:
                            st.success(f"✅ {pos}")

                in_first = primary_kw.get("in_first_paragraph", False)
                in_conclusion = primary_kw.get("in_conclusion", False)

                check_col1, check_col2 = st.columns(2)
                with check_col1:
                    if in_first:
                        st.success("✅ 冒頭段落に含まれています")
                    else:
                        st.warning("⚠️ 冒頭段落に含まれていません")
                with check_col2:
                    if in_conclusion:
                        st.success("✅ まとめに含まれています")
                    else:
                        st.warning("⚠️ まとめに含まれていません")

            st.divider()

            # Related keywords
            related_kws = keyword_analysis.get("related_keywords", [])
            if related_kws:
                st.markdown("### 🔗 関連キーワード")
                rel_data = []
                for kw in related_kws[:10]:
                    rel_data.append({
                        "キーワード": kw.get("keyword", ""),
                        "出現回数": kw.get("count", 0),
                        "密度(%)": f"{kw.get('density', 0):.2f}",
                    })
                st.dataframe(rel_data, use_container_width=True)

            # Suggestions
            suggestions = keyword_analysis.get("suggestions", [])
            if suggestions:
                st.markdown("### 💡 改善提案")
                for suggestion in suggestions:
                    st.info(f"📌 {suggestion}")
        else:
            st.info("📊 SEO分析データがありません")
            st.caption("記事生成時にSEOキーワードを設定すると分析結果が表示されます")

            # Manual analysis button
            if st.button("🔍 今すぐ分析する", key="run_seo_analysis"):
                content = article.final_content_md or article.draft_content_md or ""
                if content:
                    try:
                        from src.agents.research_agent import ResearchAgent
                        agent = ResearchAgent.__new__(ResearchAgent)
                        # Use article title keywords as target
                        target_kws = article.title.split() if article.title else []
                        if not target_kws:
                            target_kws = ["経営管理", "予算管理"]  # Default keywords
                        result = agent.analyze_keyword_density(content, target_kws[:3])
                        st.session_state["temp_keyword_analysis"] = result.to_dict()
                        st.rerun()
                    except Exception as e:
                        st.error(f"分析エラー: {e}")
                else:
                    st.warning("分析する記事コンテンツがありません")

            # Show temp analysis if exists
            if "temp_keyword_analysis" in st.session_state:
                st.success("✅ 分析完了！")
                temp_analysis = st.session_state["temp_keyword_analysis"]
                overall = temp_analysis.get("overall_seo_score", 0)
                st.metric("総合SEOスコア", f"{overall:.0f}/100")
                for sug in temp_analysis.get("suggestions", [])[:3]:
                    st.info(f"📌 {sug}")

        st.divider()

        # Competitor Keyword Analysis Section
        st.markdown("### 🔍 競合キーワード分析")
        st.caption("競合上位記事が使用しているキーワードを分析します")

        # Check for cached competitor keywords
        competitor_keywords = st.session_state.get("competitor_keywords")

        # Input for competitor keyword search
        search_query = st.text_input(
            "検索キーワード",
            value=article.title.split()[0] if article.title else "予算管理",
            key="competitor_search_query",
            help="競合分析したいキーワードを入力",
        )

        if st.button("🔎 競合キーワードを分析", key="analyze_competitor_keywords"):
            if search_query:
                with st.spinner("競合記事を分析中..."):
                    try:
                        from src.agents.research_agent import ResearchAgent
                        agent = ResearchAgent()
                        result = agent.extract_competitor_keywords(search_query, max_articles=10)
                        st.session_state["competitor_keywords"] = result.to_dict()
                        st.rerun()
                    except Exception as e:
                        st.error(f"分析エラー: {e}")
            else:
                st.warning("検索キーワードを入力してください")

        # Display competitor keywords if available
        if competitor_keywords:
            st.success(f"✅ 「{competitor_keywords.get('query', '')}」の競合分析完了")

            total = competitor_keywords.get("total_articles", 0)
            st.caption(f"分析対象: 上位{total}記事")

            keywords_data = competitor_keywords.get("keywords", [])
            if keywords_data:
                # Priority legend
                st.markdown("""
                **優先度の見方:** 🔴 必須（70%以上使用）| 🟡 推奨（40-70%使用）| 🟢 検討（40%未満）
                """)

                # Create table data
                table_data = []
                for kw in keywords_data[:15]:
                    priority = kw.get("priority", "")
                    priority_icon = "🔴" if priority == "必須" else "🟡" if priority == "推奨" else "🟢"
                    table_data.append({
                        "優先度": f"{priority_icon} {priority}",
                        "キーワード": kw.get("keyword", ""),
                        "使用率": f"{kw.get('usage_rate', 0):.0f}%",
                        "記事数": f"{kw.get('article_count', 0)}/{kw.get('total_articles', 0)}",
                        "タイトル": kw.get("found_in_titles", 0),
                        "見出し": kw.get("found_in_headings", 0),
                    })

                st.dataframe(table_data, use_container_width=True)

                # Suggestions
                suggestions = competitor_keywords.get("suggestions", [])
                if suggestions:
                    st.markdown("### 💡 推奨アクション")
                    for sug in suggestions:
                        st.info(f"📌 {sug}")

                # Show analyzed article titles
                with st.expander("📄 分析した競合記事", expanded=False):
                    titles = competitor_keywords.get("article_titles", [])
                    urls = competitor_keywords.get("article_urls", [])
                    for i, (title, url) in enumerate(zip(titles, urls), 1):
                        st.markdown(f"{i}. [{title}]({url})")

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
