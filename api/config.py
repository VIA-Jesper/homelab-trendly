from pydantic import Field
from pydantic_settings import BaseSettings

DEFAULT_PIPELINE_STEPS: list[dict] = [
    {"name": "write_draft",  "prompt_name": "generate_post", "max_attempts": 3, "is_qa_step": False},
    {"name": "optimize_seo", "prompt_name": "optimize_seo",  "max_attempts": 1, "is_qa_step": False},
    {"name": "qa_review",    "prompt_name": "qa_review",     "max_attempts": 3, "is_qa_step": True},
]


class Settings(BaseSettings):
    database_url: str
    api_key: str
    log_level: str = "INFO"
    # Pipeline steps are config-driven - add/reorder/remove steps without code changes
    pipeline_steps: list[dict] = Field(default=DEFAULT_PIPELINE_STEPS)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
