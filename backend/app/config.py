from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "sales_copilot"

    CHROMA_PERSIST_DIR: str = "./data/chroma"
    LONG_TERM_MEMORY_COLLECTION: str = "long_term_memory"

    OPENAI_API_KEY: str = ""
    MODEL_NAME: str = "deepseek-chat"
    MODEL_BASE_URL: str = "https://api.deepseek.com/v1"

    MAX_STEPS: int = 6
    MAX_HISTORY_TURNS: int = 10
    MAX_HISTORY_BEFORE_SUMMARY: int = 20
    MEMORY_IMPORTANCE_THRESHOLD: float = 0.2
    MEMORY_DAYS_TO_LIVE: int = 7

    MAX_RETRIES: int = 2
    RETRY_DELAY_SECONDS: float = 1.0

    @property
    def llm_api_key(self) -> str:
        return self.OPENAI_API_KEY

    @property
    def llm_base_url(self) -> str:
        base = self.MODEL_BASE_URL.rstrip("/")
        return base if base.endswith("/v1") else f"{base}/v1"

    @property
    def llm_model(self) -> str:
        return self.MODEL_NAME


settings = Settings()
