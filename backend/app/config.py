from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_THRESHOLDS = {"hash": 0.12, "openai": 0.3, "ollama": 0.5}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    database_url: str = "postgresql+psycopg://rag:rag@127.0.0.1:5432/rag"
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15

    embedding_provider: str = "hash"
    embedding_model: str = ""
    embedding_dim: int = 768
    llm_provider: str = "extractive"
    llm_model: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    ollama_url: str = "http://localhost:11434"

    chunk_size: int = 60
    chunk_overlap: int = 15
    top_k: int = 5
    similarity_threshold: float | None = None

    storage_backend: str = "local"
    storage_dir: str = "storage"
    s3_bucket: str = ""
    aws_region: str = ""
    max_upload_bytes: int = 10 * 1024 * 1024

    cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def threshold(self) -> float:
        if self.similarity_threshold is not None:
            return self.similarity_threshold
        return DEFAULT_THRESHOLDS.get(self.embedding_provider, 0.3)


@lru_cache
def get_settings() -> Settings:
    return Settings()
