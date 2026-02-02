"""
EPM Note Engine - Progress Indicator Component

Visual progress indicator for the article generation workflow.
"""

import streamlit as st

from src.database.models import ArticleStatus
from src.ui.state import UIPhase, get_phase_display_info


# Workflow steps in order
WORKFLOW_STEPS = [
    {
        "phase": UIPhase.ARTICLE_SELECT,
        "status": ArticleStatus.PLANNING,
        "label": "記事選択",
        "label_line1": "記事",
        "label_line2": "選択",
        "description": "記事を選択しSEOキーワードを設定",
    },
    {
        "phase": UIPhase.RESEARCH,
        "status": ArticleStatus.RESEARCHING,
        "label": "リサーチ",
        "label_line1": "リサ",
        "label_line2": "ーチ",
        "description": "競合分析と社内資料検索",
    },
    {
        "phase": UIPhase.ESSENCE_INPUT,
        "status": ArticleStatus.WAITING_INPUT,
        "label": "エッセンス入力",
        "label_line1": "エッセンス",
        "label_line2": "入力",
        "description": "失敗談・意見・知見を入力",
    },
    {
        "phase": UIPhase.DRAFTING,
        "status": ArticleStatus.DRAFTING,
        "label": "記事生成",
        "label_line1": "記事",
        "label_line2": "生成",
        "description": "AIが記事を生成",
    },
    {
        "phase": UIPhase.REVIEW,
        "status": ArticleStatus.REVIEW,
        "label": "レビュー",
        "label_line1": "レビ",
        "label_line2": "ュー",
        "description": "AIが品質をチェック",
    },
    {
        "phase": UIPhase.EDITOR,
        "status": ArticleStatus.COMPLETED,
        "label": "編集・投稿",
        "label_line1": "編集",
        "label_line2": "投稿",
        "description": "最終編集とNote投稿",
    },
]


def render_progress_indicator(
    current_phase: UIPhase,
    clickable: bool = True,
    article: "Article | None" = None,
) -> None:
    """
    Render the workflow progress indicator with clickable navigation.

    Args:
        current_phase: The current UI phase.
        clickable: Whether steps are clickable for navigation.
        article: Optional article to determine completion status based on data.
    """
    from src.ui.state import SessionState

    # Find current step index
    current_index = 0
    for i, step in enumerate(WORKFLOW_STEPS):
        if step["phase"] == current_phase:
            current_index = i
            break

    # Determine completion status based on article data
    def get_step_completion(step_index: int) -> str:
        """
        Determine if a step is completed based on article data.

        Returns: 'completed', 'current', or 'future'
        """
        phase = WORKFLOW_STEPS[step_index]["phase"]

        # If no article, use position-based logic
        if article is None:
            if step_index < current_index:
                return "completed"
            elif step_index == current_index:
                return "current"
            else:
                return "future"

        # Data-based completion check
        if phase == UIPhase.ARTICLE_SELECT:
            # Article selected = completed
            return "completed" if article else "current"

        elif phase == UIPhase.RESEARCH:
            # Has research summary = completed
            if article.research_summary:
                return "completed" if step_index < current_index else "current"
            return "future" if step_index > current_index else "current"

        elif phase == UIPhase.ESSENCE_INPUT:
            # If we're past this phase, mark as completed
            if current_index > step_index:
                return "completed"
            return "current" if step_index == current_index else "future"

        elif phase == UIPhase.DRAFTING:
            # Has draft content = completed
            if article.draft_content_md:
                return "completed" if step_index < current_index else "current"
            return "future" if step_index > current_index else "current"

        elif phase == UIPhase.REVIEW:
            # Has review score = completed
            if article.review_score and article.review_score > 0:
                return "completed" if step_index < current_index else "current"
            return "future" if step_index > current_index else "current"

        elif phase == UIPhase.EDITOR:
            # Is uploaded = completed
            if article.is_uploaded:
                return "completed"
            return "current" if step_index == current_index else "future"

        # Default fallback
        if step_index < current_index:
            return "completed"
        elif step_index == current_index:
            return "current"
        return "future"

    # Create columns for each step (with arrow separators)
    # Pattern: [step] [→] [step] [→] ...
    num_steps = len(WORKFLOW_STEPS)
    col_widths = []
    for i in range(num_steps):
        col_widths.append(3)  # Step column
        if i < num_steps - 1:
            col_widths.append(1)  # Arrow column

    cols = st.columns(col_widths)

    col_index = 0
    for i, step in enumerate(WORKFLOW_STEPS):
        with cols[col_index]:
            # Determine step state based on data
            state = get_step_completion(i)

            if state == "completed":
                icon = "✅"
            elif state == "current":
                icon = "🔵"
            else:
                icon = "⚪"

            step_num = i + 1

            # Create clickable button with custom styling
            if clickable:
                # Use unique key for each button
                button_key = f"nav_step_{i}_{step['phase'].value}"

                # Determine button style based on state
                if state == "current":
                    button_type = "primary"
                else:
                    button_type = "secondary"

                # Create button with step number, icon and 2-line label
                button_label = f"{step_num}.{icon}\n{step['label_line1']}\n{step['label_line2']}"

                if st.button(
                    button_label,
                    key=button_key,
                    type=button_type,
                    use_container_width=True,
                    help=step['description'],
                ):
                    # Navigate to the clicked phase
                    if step["phase"] != current_phase:
                        SessionState.set_ui_phase(step["phase"])
                        st.rerun()
            else:
                # Non-clickable display (original behavior)
                if state == "completed":
                    color = "green"
                elif state == "current":
                    color = "blue"
                else:
                    color = "gray"

                st.markdown(
                    f"<div style='text-align: center;'>"
                    f"<span style='font-size: 0.8em; color: {color};'>STEP{step_num}</span><br>"
                    f"<span style='font-size: 1.5em;'>{icon}</span><br>"
                    f"<span style='font-size: 0.8em; color: {color};'>{step['label_line1']}<br>{step['label_line2']}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        col_index += 1

        # Add arrow between steps
        if i < num_steps - 1:
            with cols[col_index]:
                # Arrow indicator
                prev_state = get_step_completion(i)
                if prev_state == "completed":
                    arrow_color = "#28a745"  # Green
                    arrow = "▶▶"
                elif prev_state == "current":
                    arrow_color = "#007bff"  # Blue
                    arrow = "▶▶"
                else:
                    arrow_color = "#6c757d"  # Gray
                    arrow = "▷▷"

                st.markdown(
                    f"<div style='text-align: center; padding-top: 25px;'>"
                    f"<span style='font-size: 1.5em; color: {arrow_color}; font-weight: bold;'>{arrow}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            col_index += 1

    # Progress bar
    progress = (current_index + 1) / len(WORKFLOW_STEPS)
    st.progress(progress)


def render_phase_header(current_phase: UIPhase) -> None:
    """
    Render a header for the current phase.

    Args:
        current_phase: The current UI phase.
    """
    info = get_phase_display_info(current_phase)

    # Find step description
    description = ""
    for step in WORKFLOW_STEPS:
        if step["phase"] == current_phase:
            description = step["description"]
            break

    st.markdown(
        f"### {info['icon']} {info['label']}"
    )
    if description:
        st.caption(description)


def render_processing_indicator(message: str = "処理中...") -> None:
    """
    Render a processing indicator for long-running operations.

    Args:
        message: The message to display.
    """
    with st.spinner(message):
        st.empty()


def render_step_card(
    step_number: int,
    title: str,
    description: str,
    is_complete: bool = False,
    is_current: bool = False,
) -> None:
    """
    Render a step card in the progress indicator.

    Args:
        step_number: The step number (1-based).
        title: The step title.
        description: The step description.
        is_complete: Whether this step is complete.
        is_current: Whether this is the current step.
    """
    if is_complete:
        icon = "✅"
        border_color = "#28a745"
    elif is_current:
        icon = "🔵"
        border_color = "#007bff"
    else:
        icon = f"{step_number}"
        border_color = "#6c757d"

    st.markdown(
        f"""
        <div style="
            border: 2px solid {border_color};
            border-radius: 10px;
            padding: 10px;
            margin: 5px 0;
            background-color: {'#f8f9fa' if not is_current else '#e7f3ff'};
        ">
            <span style="font-size: 1.2em; font-weight: bold;">{icon} {title}</span>
            <br>
            <span style="font-size: 0.85em; color: #666;">{description}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_compact_progress(current_phase: UIPhase) -> None:
    """
    Render a compact progress indicator for the sidebar.

    Args:
        current_phase: The current UI phase.
    """
    # Find current step index
    current_index = 0
    for i, step in enumerate(WORKFLOW_STEPS):
        if step["phase"] == current_phase:
            current_index = i
            break

    st.caption("進捗状況")

    # Compact display
    progress_text = " → ".join([
        f"**{step['label']}**" if i == current_index
        else f"~~{step['label']}~~" if i < current_index
        else step['label']
        for i, step in enumerate(WORKFLOW_STEPS)
    ])

    st.markdown(progress_text)

    # Simple progress bar
    progress = (current_index + 1) / len(WORKFLOW_STEPS)
    st.progress(progress)
