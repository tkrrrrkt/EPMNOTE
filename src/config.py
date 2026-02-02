"""
EPM Note Engine - Configuration Management

Centralized configuration using Pydantic Settings for type-safe environment variable handling.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        enable_decoding=False,
    )

    # ===========================================
    # Database Configuration
    # ===========================================
    postgres_user: str = Field(default="epmuser", description="PostgreSQL username")
    postgres_password: str = Field(default="epmpass", description="PostgreSQL password")
    postgres_db: str = Field(default="epm_note", description="PostgreSQL database name")
    postgres_host: str = Field(default="localhost", description="PostgreSQL host")
    postgres_port: int = Field(default=5432, description="PostgreSQL port")

    @property
    def database_url(self) -> str:
        """Construct database URL from individual components."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        """Construct async database URL for SQLAlchemy async engine."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ===========================================
    # AI API Keys
    # ===========================================
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key for Claude",
    )
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key for GPT-4o",
    )
    tavily_api_key: str = Field(
        default="",
        description="Tavily API key for SEO research",
    )
    tavily_include_domains: list[str] = Field(
        default_factory=list,
        description="Preferred domains to include for Tavily search",
    )
    tavily_exclude_domains: list[str] = Field(
        default_factory=list,
        description="Domains to exclude for Tavily search",
    )
    tavily_prefer_domains: list[str] = Field(
        default_factory=list,
        description="Domains to prioritize in Tavily results (soft preference)",
    )

    # ===========================================
    # Note.com Credentials
    # ===========================================
    note_email: str = Field(
        default="",
        description="Note.com login email",
    )
    note_password: str = Field(
        default="",
        description="Note.com login password",
    )

    # ===========================================
    # ChromaDB Configuration
    # ===========================================
    chroma_persist_directory: str = Field(
        default="./data/chroma_db",
        description="ChromaDB persistence directory",
    )

    @property
    def chroma_path(self) -> Path:
        """Get ChromaDB path as Path object."""
        return Path(self.chroma_persist_directory)

    # ===========================================
    # Application Settings
    # ===========================================
    streamlit_port: int = Field(default=8501, description="Streamlit server port")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Logging level",
    )
    max_review_iterations: int = Field(
        default=1,
        description="Maximum number of review iterations before forcing completion",
    )
    generation_timeout: int = Field(
        default=300,
        description="Article generation timeout in seconds (5 minutes default)",
    )

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is uppercase."""
        return v.upper() if isinstance(v, str) else v

    @field_validator("tavily_include_domains", "tavily_exclude_domains", "tavily_prefer_domains", mode="before")
    @classmethod
    def parse_domain_list(cls, v):
        """Parse comma-separated domain lists from env."""
        if v is None:
            return []
        if isinstance(v, list):
            return [s.strip() for s in v if str(s).strip()]
        if isinstance(v, str):
            parts = [p.strip() for p in v.replace("\n", ",").split(",")]
            return [p for p in parts if p]
        return []

    def validate_api_keys(self) -> dict[str, bool]:
        """
        Validate that required API keys are configured.

        Returns:
            Dictionary with API name as key and validity status as value.
        """
        return {
            "anthropic": bool(self.anthropic_api_key and self.anthropic_api_key.startswith("sk-ant-")),
            "openai": bool(self.openai_api_key and self.openai_api_key.startswith("sk-")),
            "tavily": bool(self.tavily_api_key and self.tavily_api_key.startswith("tvly-")),
            "note_credentials": bool(self.note_email and self.note_password),
        }

    def check_required_apis(self, required: list[str] | None = None) -> None:
        """
        Check if required API keys are configured. Raises ValueError if not.

        Args:
            required: List of required API names. Defaults to all APIs.

        Raises:
            ValueError: If any required API key is missing or invalid.
        """
        if required is None:
            required = ["anthropic", "openai", "tavily"]

        validation = self.validate_api_keys()
        missing = [api for api in required if not validation.get(api, False)]

        if missing:
            raise ValueError(
                f"Missing or invalid API keys: {', '.join(missing)}. "
                "Please check your .env file."
            )


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached application settings.

    Uses lru_cache to ensure settings are loaded only once.

    Returns:
        Settings instance with loaded configuration.
    """
    return Settings()


def _dedupe_domains(domains: list[str]) -> list[str]:
    """Deduplicate domains while preserving order."""
    seen: set[str] = set()
    normalized: list[str] = []
    for domain in domains:
        cleaned = domain.strip().lower()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def get_tavily_domain_profiles() -> dict[str, dict[str, list[str]]]:
    """
    Return predefined Tavily domain profiles.

    Profiles are intentionally opinionated to support different research goals.
    """
    core_trusted = [
        "meti.go.jp",
        "soumu.go.jp",
        "jstage.jst.go.jp",
        "imanet.org",
        "sfmagazine.com",
        "aicpa-cima.com",
        "financialprofessionals.org",
        "cfo.com",
        "cfo.jp",
        "fpa-trends.com",
        "gartner.com",
        "forrester.com",
        "mckinsey.com",
        "deloitte.com",
        "ey.com",
        "kpmg.com",
        "pwc.com",
        "bcg.com",
        "sloanreview.mit.edu",
    ]
    vendor_official = [
        "microsoft.com",
        "learn.microsoft.com",
        "oracle.com",
        "sap.com",
        "workiva.com",
        "onestream.com",
        "planful.com",
        "anaplan.com",
        "board.com",
        "jedox.com",
        "pigment.com",
        "datarails.com",
        "highradius.com",
        "loglass.co.jp",
        "loglass.jp",
        "diggle.jp",
        "biz.moneyforward.com",
    ]
    market_compare = [
        "boxil.jp",
        "it-trend.jp",
        "itreview.jp",
        "saas.imitsu.jp",
    ]
    noisy_sources = [
        "note.com",
        "prtimes.jp",
        "atpress.ne.jp",
        "similarweb.com",
        "emergenresearch.com",
        "grandviewresearch.com",
    ]

    return {
        "balanced": {
            "include_domains": [],
            "exclude_domains": _dedupe_domains(noisy_sources),
            "prefer_domains": _dedupe_domains(core_trusted + vendor_official),
        },
        "evidence": {
            "include_domains": _dedupe_domains(core_trusted),
            "exclude_domains": _dedupe_domains(noisy_sources),
            "prefer_domains": _dedupe_domains(core_trusted),
        },
        "market": {
            "include_domains": [],
            "exclude_domains": _dedupe_domains(["note.com", "prtimes.jp", "atpress.ne.jp"]),
            "prefer_domains": _dedupe_domains(core_trusted + vendor_official + market_compare),
        },
    }


def resolve_tavily_domains(
    profile: str | None,
    settings: Settings | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """
    Resolve Tavily domain filters for a given profile.

    If profile is unknown or None, fall back to environment settings.
    """
    settings = settings or get_settings()
    profiles = get_tavily_domain_profiles()
    if profile and profile in profiles:
        chosen = profiles[profile]
        return (
            chosen.get("include_domains", []),
            chosen.get("exclude_domains", []),
            chosen.get("prefer_domains", []),
        )
    return (
        settings.tavily_include_domains,
        settings.tavily_exclude_domains,
        settings.tavily_prefer_domains,
    )


# ===========================================
# API Client Factories
# ===========================================

def get_anthropic_client():
    """
    Get configured Anthropic client.

    Returns:
        Anthropic client instance.

    Raises:
        ValueError: If API key is not configured.
    """
    from anthropic import Anthropic

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY is not configured")

    return Anthropic(api_key=settings.anthropic_api_key)


def get_openai_client():
    """
    Get configured OpenAI client.

    Returns:
        OpenAI client instance.

    Raises:
        ValueError: If API key is not configured.
    """
    from openai import OpenAI

    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")

    return OpenAI(api_key=settings.openai_api_key)


def get_tavily_client():
    """
    Get configured Tavily client.

    Returns:
        TavilyClient instance.

    Raises:
        ValueError: If API key is not configured.
    """
    from tavily import TavilyClient

    settings = get_settings()
    if not settings.tavily_api_key:
        raise ValueError("TAVILY_API_KEY is not configured")

    return TavilyClient(api_key=settings.tavily_api_key)


def get_chroma_client():
    """
    Get configured ChromaDB persistent client.

    Returns:
        ChromaDB PersistentClient instance.
    """
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    settings = get_settings()

    # Ensure directory exists
    settings.chroma_path.mkdir(parents=True, exist_ok=True)

    return chromadb.PersistentClient(
        path=str(settings.chroma_path),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
