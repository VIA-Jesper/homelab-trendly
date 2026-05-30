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

    # Pipeline steps are config-driven — add/reorder/remove without code changes
    pipeline_steps: list[dict] = Field(default=DEFAULT_PIPELINE_STEPS)

    # ── husforbegyndere.dk ─────────────────────────────────────────────────────
    # Loaded from .env. pr_hus_partner_id is required for PriceRunner widget
    # embeds — without it the widget inserter falls back to a plain HTML card.
    pr_hus_partner_id: str = ""
    wp_hus_url: str = ""
    wp_hus_user: str = ""
    wp_hus_pass: str = ""

    # Load api/.env first (DATABASE_URL, API_KEY), then root .env (WP_*, PR_*).
    # Values in api/.env take precedence. This keeps DB config local while site
    # credentials stay in the root .env alongside docker-compose.
    model_config = {"env_file": ["../.env", ".env"], "env_file_encoding": "utf-8"}


settings = Settings()
