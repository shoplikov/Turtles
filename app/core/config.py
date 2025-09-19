import os
from functools import lru_cache
from dotenv import load_dotenv


# Load environment variables from a .env file if present
load_dotenv()


class Settings:
    """Application settings sourced from environment variables.

    Secrets should be provided via environment variables or a .env file.
    """

    def __init__(self) -> None:
        # Server
        self.app_host: str = os.getenv("APP_HOST", "0.0.0.0")
        self.app_port: int = int(os.getenv("APP_PORT", "8000"))

        # Jira configuration
        self.jira_base_url: str = os.getenv("JIRA_BASE_URL", "")
        self.jira_email: str = os.getenv("JIRA_EMAIL", "")
        self.jira_api_token: str = os.getenv("JIRA_API_TOKEN", "")

        # OpenAI / LLM configuration
        self.openai_base_url: str = os.getenv("OPENAI_BASE_URL", "")
        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
        self.openai_model: str = os.getenv("OPENAI_MODEL", "llama4scout")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


