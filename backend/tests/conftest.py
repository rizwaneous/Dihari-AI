import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db as dbmod
from app.modules.abuse import limiter
from app.settings import get_settings

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("DEV_MODE", "true")
    # Tests must not depend on a developer's backend/.env (real keys, raised demo limits, Gemini providers).
    for k, v in {"ASR_PROVIDERS": "mock", "TTS_PROVIDERS": "mock", "LLM_EXTRACT_PROVIDERS": "mock-a",
                 "LLM_VERIFY_PROVIDERS": "mock-b", "GEMINI_API_KEY": "", "MOCK_ASR_FIXED_TEXT": "",
                 "MAX_POSTS_PER_HIRER_PER_HOUR": "5", "MAX_OPEN_JOBS_PER_HIRER": "5", "MAX_JOBS_PER_HIRER_PER_DAY": "10",
                 "RATE_LIMIT_ENABLED": "true", "SCHEDULER_ENABLED": "false", "SMS_PROVIDER": "stub",
                 "NOTIFY_PROVIDERS": "log", "DEMO_LOGINS": "true", "DEFAULT_COUNTRY": "PK"}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    dbmod.init_db("sqlite://")
    limiter.reset()
    from app.db import CLOCK
    from datetime import timedelta
    CLOCK.offset = timedelta(0)
    yield
    get_settings.cache_clear()


@pytest.fixture
def db():
    s = dbmod.SessionLocal()
    yield s
    s.close()


@pytest.fixture
def client():
    from app.main import create_app
    with TestClient(create_app()) as c:
        yield c


def login(client, phone, role):
    r = client.post("/auth/request-otp", json={"phone": phone})
    assert r.status_code == 200, r.text
    code = r.json()["dev_otp"]
    r = client.post("/auth/verify-otp", json={"phone": phone, "code": code, "role": role})
    assert r.status_code == 200, r.text
    d = r.json()
    return {"Authorization": f"Bearer {d['token']}"}, d["user_id"]


@pytest.fixture
def make_user(client):
    def _mk(phone, role):
        return login(client, phone, role)
    return _mk
