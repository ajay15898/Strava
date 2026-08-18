from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://pace:pace@localhost:5432/pace"

    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_redirect_uri: str = "http://localhost:8000/api/auth/strava/callback"
    strava_webhook_verify_token: str = ""

    # Coach LLM. Any OpenAI-compatible chat-completions endpoint; the provider
    # is a config concern, never a code concern. The coach paraphrases a
    # pre-computed context and is numerically fenced by coach/verify.py, so
    # model capability is a comfort rather than a correctness requirement.
    coach_base_url: str = "https://api.groq.com/openai/v1"
    coach_model: str = "llama-3.3-70b-versatile"
    coach_api_key: str = ""
    coach_temperature: float = 0.2
    coach_timeout_s: float = 60.0

    session_secret: str = "dev-only-change-me"
    frontend_origin: str = "http://localhost:5173"

    @property
    def coach_configured(self) -> bool:
        return bool(self.coach_api_key and self.coach_base_url and self.coach_model)


@lru_cache
def get_settings() -> Settings:
    return Settings()
