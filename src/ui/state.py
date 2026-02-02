"""
EPM Note Engine - Session State Management

Manages Streamlit session state and synchronization with LangGraph workflow state.
"""

import enum
from dataclasses import dataclass, field
from typing import Any

import streamlit as st

from src.database.models import ArticleStatus


class UIPhase(str, enum.Enum):
    """UI display phases."""

    ARTICLE_SELECT = "article_select"  # Sidebar - selecting article
    RESEARCH = "research"  # Research in progress
    ESSENCE_INPUT = "essence_input"  # InputForm - entering essence
    DRAFTING = "drafting"  # AI generating draft
    REVIEW = "review"  # AI reviewing draft
    EDITOR = "editor"  # Editor - final editing
    UPLOAD = "upload"  # Uploading to Note.com


@dataclass
class WorkflowState:
    """
    Mirror of LangGraph ArticleState for UI synchronization.

    This keeps the UI state in sync with the workflow engine.
    """

    article_id: str | None = None
    phase: str = "research"
    seo_keywords: str = ""
    research_summary: str = ""
    essences: list[dict[str, Any]] = field(default_factory=list)
    draft_content: str = ""
    review_score: int = 0
    review_feedback: str = ""
    retry_count: int = 0


class SessionState:
    """
    Centralized session state manager for Streamlit.

    Provides type-safe access to session state variables and
    handles synchronization with LangGraph workflow state.
    """

    # Session state keys
    KEY_CURRENT_ARTICLE_ID = "current_article_id"
    KEY_WORKFLOW_STATE = "workflow_state"
    KEY_UI_PHASE = "ui_phase"
    KEY_MESSAGES = "messages"
    KEY_IS_PROCESSING = "is_processing"

    @classmethod
    def initialize(cls) -> None:
        """Initialize all session state variables with defaults."""
        if cls.KEY_CURRENT_ARTICLE_ID not in st.session_state:
            st.session_state[cls.KEY_CURRENT_ARTICLE_ID] = None

        if cls.KEY_WORKFLOW_STATE not in st.session_state:
            st.session_state[cls.KEY_WORKFLOW_STATE] = WorkflowState()

        if cls.KEY_UI_PHASE not in st.session_state:
            st.session_state[cls.KEY_UI_PHASE] = UIPhase.ARTICLE_SELECT

        if cls.KEY_MESSAGES not in st.session_state:
            st.session_state[cls.KEY_MESSAGES] = []

        if cls.KEY_IS_PROCESSING not in st.session_state:
            st.session_state[cls.KEY_IS_PROCESSING] = False

    @classmethod
    def get_current_article_id(cls) -> str | None:
        """Get the currently selected article ID."""
        return st.session_state.get(cls.KEY_CURRENT_ARTICLE_ID)

    @classmethod
    def set_current_article_id(cls, article_id: str | None) -> None:
        """Set the currently selected article ID."""
        st.session_state[cls.KEY_CURRENT_ARTICLE_ID] = article_id
        # Reset workflow state when article changes
        if article_id:
            workflow = cls.get_workflow_state()
            workflow.article_id = article_id
            cls.set_workflow_state(workflow)

    @classmethod
    def get_workflow_state(cls) -> WorkflowState:
        """Get the current workflow state."""
        return st.session_state.get(cls.KEY_WORKFLOW_STATE, WorkflowState())

    @classmethod
    def set_workflow_state(cls, state: WorkflowState) -> None:
        """Set the workflow state."""
        st.session_state[cls.KEY_WORKFLOW_STATE] = state

    @classmethod
    def get_ui_phase(cls) -> UIPhase:
        """Get the current UI phase."""
        return st.session_state.get(cls.KEY_UI_PHASE, UIPhase.ARTICLE_SELECT)

    @classmethod
    def set_ui_phase(cls, phase: UIPhase) -> None:
        """Set the current UI phase."""
        st.session_state[cls.KEY_UI_PHASE] = phase

    @classmethod
    def is_processing(cls) -> bool:
        """Check if a background process is running."""
        return st.session_state.get(cls.KEY_IS_PROCESSING, False)

    @classmethod
    def set_processing(cls, is_processing: bool) -> None:
        """Set the processing state."""
        st.session_state[cls.KEY_IS_PROCESSING] = is_processing

    @classmethod
    def add_message(cls, message: str, type: str = "info") -> None:
        """Add a message to display to the user."""
        messages = st.session_state.get(cls.KEY_MESSAGES, [])
        messages.append({"text": message, "type": type})
        st.session_state[cls.KEY_MESSAGES] = messages

    @classmethod
    def get_messages(cls) -> list[dict[str, str]]:
        """Get all pending messages."""
        return st.session_state.get(cls.KEY_MESSAGES, [])

    @classmethod
    def clear_messages(cls) -> None:
        """Clear all pending messages."""
        st.session_state[cls.KEY_MESSAGES] = []

    @classmethod
    def sync_from_article_status(cls, status: ArticleStatus) -> None:
        """
        Synchronize UI phase based on article status.

        Args:
            status: The article's current status from the database.
        """
        status_to_phase = {
            ArticleStatus.PLANNING: UIPhase.ARTICLE_SELECT,
            ArticleStatus.RESEARCHING: UIPhase.RESEARCH,
            ArticleStatus.WAITING_INPUT: UIPhase.ESSENCE_INPUT,
            ArticleStatus.DRAFTING: UIPhase.DRAFTING,
            ArticleStatus.REVIEW: UIPhase.REVIEW,
            ArticleStatus.COMPLETED: UIPhase.EDITOR,
        }
        cls.set_ui_phase(status_to_phase.get(status, UIPhase.ARTICLE_SELECT))

    @classmethod
    def reset(cls) -> None:
        """Reset all session state to defaults."""
        st.session_state[cls.KEY_CURRENT_ARTICLE_ID] = None
        st.session_state[cls.KEY_WORKFLOW_STATE] = WorkflowState()
        st.session_state[cls.KEY_UI_PHASE] = UIPhase.ARTICLE_SELECT
        st.session_state[cls.KEY_MESSAGES] = []
        st.session_state[cls.KEY_IS_PROCESSING] = False


def get_phase_display_info(phase: UIPhase) -> dict[str, str]:
    """
    Get display information for a UI phase.

    Args:
        phase: The UI phase.

    Returns:
        Dictionary with 'label', 'icon', and 'color' keys.
    """
    phase_info = {
        UIPhase.ARTICLE_SELECT: {
            "label": "記事選択",
            "icon": "📋",
            "color": "gray",
        },
        UIPhase.RESEARCH: {
            "label": "リサーチ中",
            "icon": "🔍",
            "color": "blue",
        },
        UIPhase.ESSENCE_INPUT: {
            "label": "エッセンス入力",
            "icon": "✏️",
            "color": "orange",
        },
        UIPhase.DRAFTING: {
            "label": "記事生成中",
            "icon": "🤖",
            "color": "purple",
        },
        UIPhase.REVIEW: {
            "label": "レビュー中",
            "icon": "📝",
            "color": "yellow",
        },
        UIPhase.EDITOR: {
            "label": "編集",
            "icon": "📄",
            "color": "green",
        },
        UIPhase.UPLOAD: {
            "label": "アップロード中",
            "icon": "🚀",
            "color": "red",
        },
    }
    return phase_info.get(phase, {"label": "不明", "icon": "❓", "color": "gray"})
