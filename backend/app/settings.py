from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_root() -> Path:
    here = Path(__file__).resolve()
    for p in here.parents:
        if (p / "config").is_dir() and (p / "locales").is_dir():
            return p
    return here.parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./dihari.db"
    secret_key: str = "dev-secret-change-me"
    dev_mode: bool = True
    default_country: str = "PK"
    config_dir: str = str(_find_root() / "config")
    locales_dir: str = str(_find_root() / "locales")
    token_ttl_hours: int = 24 * 30

    # OTP / SMS
    sms_provider: str = "stub"
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 5

    # AI provider chains (comma separated, first = primary). Real providers are added later.
    asr_providers: str = "mock"
    tts_providers: str = "mock"
    llm_extract_providers: str = "mock-a"
    llm_verify_providers: str = "mock-b"
    mock_asr_fixed_text: str = ""

    # Notifications
    notify_providers: str = "log"          # order: first that works wins; sms fallback is last
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    vapid_subject: str = ""
    vapid_public_key: str = ""
    vapid_private_key: str = ""

    # Abuse controls
    rate_limit_enabled: bool = True
    max_jobs_per_hirer_per_day: int = 10
    max_open_jobs_per_hirer: int = 5
    reports_to_flag_job: int = 3
    geo_fuzz_max_m: int = 500
    geo_fuzz_min_m: int = 150

    scheduler_enabled: bool = False
    scheduler_interval_seconds: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()
