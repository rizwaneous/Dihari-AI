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

    # Google Gemini (one key → extraction, speech-to-text, text-to-speech). Comma lists = fallback order.
    gemini_api_key: str = ""
    gemini_text_models: str = "gemini-flash-lite-latest,gemini-3.5-flash,gemini-flash-latest"
    gemini_asr_models: str = "gemini-flash-lite-latest,gemini-3.5-flash"
    gemini_tts_models: str = "gemini-3.8-flash-tts,gemini-2.5-flash-preview-tts"
    gemini_tts_voice: str = "Kore"
    gemini_thinking_level: str = "low"
    gemini_timeout_seconds: float = 20

    # Notifications
    notify_providers: str = "log"          # order: first that works wins; sms fallback is last
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    whatsapp_token: str = ""
    whatsapp_phone_id: str = ""
    whatsapp_template: str = ""
    vapid_subject: str = ""
    vapid_public_key: str = ""
    vapid_private_key: str = ""

    # Abuse controls
    rate_limit_enabled: bool = True
    max_jobs_per_hirer_per_day: int = 10
    max_posts_per_hirer_per_hour: int = 5
    demo_logins: bool = True
    demo_hirer_phone: str = "03001000000"
    demo_worker_phone: str = "03002000000"   # one-tap demo accounts; only ever active while DEV_MODE is true
    max_open_jobs_per_hirer: int = 5
    reports_to_flag_job: int = 3
    geo_fuzz_max_m: int = 500
    geo_fuzz_min_m: int = 150

    scheduler_enabled: bool = False
    scheduler_interval_seconds: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()
