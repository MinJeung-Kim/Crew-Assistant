from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # LLM
    llm_provider: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str

    # Server
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_env: str = "development"

    # CORS
    cors_origins: str = "http://localhost:3000"

    # CrewAI
    crewai_enabled: bool = True
    crewai_model: str = ""
    crewai_web_search_results: int = Field(default=6, ge=1, le=12)

    # RAG
    rag_enabled: bool = True
    rag_storage_path: str = "./data/knowledge"
    rag_embedding_model: str = "text-embedding-3-small"
    rag_top_k: int = Field(default=4, ge=1, le=12)
    rag_max_chunk_chars: int = Field(default=900, ge=300, le=3000)
    rag_chunk_overlap: int = Field(default=120, ge=0, le=500)
    rag_max_upload_mb: int = Field(default=20, ge=1, le=200)

    # Google Drive shared context for chat
    google_drive_context_enabled: bool = True
    google_drive_context_results: int = Field(default=4, ge=1, le=12)
    google_drive_context_max_chars: int = Field(default=1400, ge=300, le=6000)
    google_drive_context_max_file_bytes: int = Field(default=4_000_000, ge=100_000, le=20_000_000)

    # Integrations (Env page)
    google_api_key: str = ""
    slack_api_key: str = ""
    slack_invite_link: str = ""
    slack_team_id: str = ""
    onboarding_drive_file_limit: int = Field(default=8, ge=1, le=20)
    google_oauth_token_path: str = "./data/oauth/token.json"
    google_oauth_installed_port: int = Field(default=8080, ge=1, le=65535)

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
