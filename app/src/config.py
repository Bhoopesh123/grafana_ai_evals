import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    generation_model: str = os.getenv("GENERATION_MODEL", "gpt-4.1-mini")
    judge_model: str = os.getenv("JUDGE_MODEL", "gpt-4.1-mini")
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    eval_sample_rate: float = float(os.getenv("EVAL_SAMPLE_RATE", "1.0"))
    rubric_version: str = os.getenv("EVAL_RUBRIC_VERSION", "v1")
    capture_content: bool = os.getenv("CAPTURE_CONTENT", "false").lower() == "true"

    def require_openai_key(self) -> None:
        if not self.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is empty. Add it to .env and restart the app.")


settings = Settings()
