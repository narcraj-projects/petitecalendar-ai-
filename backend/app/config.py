"""Server configuration; never serialize database credentials."""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    supabase_url: str = ""
    publishable_key: str = ""
    database_url: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    token_encryption_key: str = ""
    app_base_url: str = "http://127.0.0.1:8017"
    resend_api_key: str = ""
    email_from: str = ""
    ai_enabled: bool = False
    staging_private: bool = False
    staging_access_password: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-6-astra"

    @property
    def email_configured(self) -> bool:
        return bool(self.resend_api_key and self.email_from and self.token_encryption_key)

    @property
    def google_configured(self) -> bool:
        return bool(
            self.google_client_id and self.google_client_secret and self.token_encryption_key
        )

    @property
    def google_callback_url(self) -> str:
        return self.app_base_url.rstrip("/") + "/api/integrations/google/callback"

    @property
    def auth_configured(self) -> bool:
        return bool(self.supabase_url and self.publishable_key)

    @property
    def issuer(self) -> str:
        return self.supabase_url.rstrip("/") + "/auth/v1"


@lru_cache
def get_settings() -> Settings:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    return Settings(
        supabase_url=os.getenv("SUPABASE_URL", "").strip().rstrip("/"),
        publishable_key=os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip(),
        database_url=os.getenv("DATABASE_URL", "").strip(),
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
        token_encryption_key=os.getenv("TOKEN_ENCRYPTION_KEY", "").strip(),
        app_base_url=os.getenv("APP_BASE_URL", "http://127.0.0.1:8017").strip().rstrip("/"),
        resend_api_key=os.getenv("RESEND_API_KEY", "").strip(),
        email_from=os.getenv("EMAIL_FROM", "").strip(),
        ai_enabled=os.getenv("AI_ENABLED", "false").strip().lower() == "true",
        staging_private=os.getenv("STAGING_PRIVATE", "false").strip().lower() == "true",
        staging_access_password=os.getenv("STAGING_ACCESS_PASSWORD", ""),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-6-astra").strip(),
    )
