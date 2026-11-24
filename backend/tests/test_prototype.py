"""Prototype features: demo logins, worker tiers, Kaam Card stats, fair-rate hint, Gemini provider, review bug fixes."""
import base64
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.modules import wage_floor


def job_body(**kw):
    start = datetime.now(timezone.utc) + timedelta(days=1)
    b = dict(task="tile", headcount=2, location_text="G-13", start_at=start.isoformat(), daily_rate=1500,
             hours_per_day=8, payment_day=(start + timedelta(days=1)).date().isoformat())
    b.update(kw)
    return b


def demo(client, role):
    r = client.post("/auth/demo-login", json={"role": role})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_demo_accounts_post_and_book_many_jobs(client):
    info = client.get("/auth/demo").json()
    assert info["enabled"] and {a["role"] for a in info["accounts"]} == {"hirer", "worker"}
    hirer, worker = demo(client, "hirer"), demo(client, "worker")
    assert client.get("/profiles/me", headers=hirer).json()["role"] == "hirer"
    me = client.get("/profiles/me", headers=worker).json()
    assert me["role"] == "worker" and me["profile"]["lat"] is not None
    ids = []
    for i, task in enumerate(["tile", "paint", "mason"]):
        r = client.post("/jobs", headers=hirer, json=job_body(task=task, daily_rate=1500 + 100 * i))
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    feed = {j["id"] for j in client.get(f"/jobs/nearby?all_trades=true", headers=worker).json()}
    assert set(ids) <= feed
    for jid in ids:
        assert client.post(f"/jobs/{jid}/book", headers=worker).status_code == 200
    work = client.get("/my/work", headers=worker).json()
    assert {w["job"]["id"] for w in work if w["status"] == "confirmed"} == set(ids)


def test_demo_login_disabled_outside_dev_mode(client, monkeypatch):
    from app.settings import get_settings
    monkeypatch.setattr(get_settings(), "dev_mode", False)
    assert client.get("/auth/demo").json() == {"enabled": False, "accounts": []}
    assert client.post("/auth/demo-login", json={"role": "hirer"}).status_code == 404


def test_demo_worker_has_tier_and_kaam_card(client):
    worker = demo(client, "worker")
    demo(client, "worker")   # idempotent: history is not duplicated
    s = client.get("/my/stats", headers=worker).json()
    assert len(s["history"]) == 7 and all(h["proof"] for h in s["history"])
    assert s["tier"]["code"] == "bharosemand" and s["tier"]["next"]["code"] == "ustad"
    assert s["earned_month"] > 0 and s["earned_total"] >= s["earned_month"] and s["owed"] == 0


def test_tier_rules_and_smoothing():
    from app.modules import reputation
    assert reputation.smoothed_rating(5, 1) == pytest.approx((5 + 4 * 3.5) / 5)
    assert reputation.smoothed_rating(0, 0) is None
    tiers = reputation.tier_rules()["tiers"]
    assert [t["code"] for t in tiers] == ["naya", "bharosemand", "ustad", "ustad_gold"]
    assert reputation._qualifies(tiers[1], 5, 0.9, 4.0, 1) and not reputation._qualifies(tiers[1], 5, 0.8, 4.0, 1)


def test_new_worker_is_naya_and_offers_show_tier(client, make_user):
    hirer, _ = make_user("+923001234001", "hirer")
    worker, _ = make_user("+923001234002", "worker")
    jid = client.post("/jobs", headers=hirer, json=job_body()).json()["id"]
    client.post(f"/jobs/{jid}/offers", headers=worker, json={"rate": 1600}).raise_for_status()
    offers = client.get(f"/jobs/{jid}/offers", headers=hirer).json()
    assert offers[0]["tier"]["code"] == "naya"


def test_fair_rate_hint(client, make_user):
    hirer, _ = make_user("+923001234011", "hirer")
    for rate in (1400, 1600, 1800):
        client.post("/jobs", headers=hirer, json=job_body(daily_rate=rate, start_at=(datetime.now(timezone.utc) + timedelta(days=1, hours=rate // 100)).isoformat())).raise_for_status()
    r = client.get("/jobs/fair-rate?task=tile&location_text=G-13", headers=hirer).json()
    assert r["median"] == 1600 and r["count"] == 3 and r["floor"] == 1000 and r["suggested"] == 1600


def test_withdraw_offer_no_longer_crashes(client, make_user):
    hirer, _ = make_user("+923001234021", "hirer")
    worker, _ = make_user("+923001234022", "worker")
    jid = client.post("/jobs", headers=hirer, json=job_body()).json()["id"]
    oid = client.post(f"/jobs/{jid}/offers", headers=worker, json={}).json()["id"]
    assert client.delete(f"/jobs/offers/{oid}", headers=worker).json() == {"ok": True}


def test_bad_deductions_rejected_cleanly(client, make_user):
    hirer, _ = make_user("+923001234031", "hirer")
    r = client.post("/jobs", headers=hirer, json=job_body(deductions=[{"label": "x", "amount": "abc"}]))
    assert r.status_code == 422
    r = client.post("/jobs", headers=hirer, json=job_body(deductions=[{"label": "x", "amount": -500}]))
    assert r.status_code == 422
    chk = wage_floor.check(country="PK", region="ICT", daily_rate=1000, hours_per_day=8, payment_day=None, start_date=None,
                           deductions=[{"label": "bonus", "amount": -900}, {"label": "food", "amount": "x"}])
    assert [v.code for v in chk.violations].count("hidden_deduction") == 2


def test_login_does_not_flip_existing_role(client, make_user):
    make_user("+923001234041", "worker")
    from tests.conftest import login
    _, uid = login(client, "+923001234041", "hirer")
    hdr, _ = login(client, "+923001234041", None)
    assert client.get("/profiles/me", headers=hdr).json()["role"] == "worker"


# ---------------- Gemini provider (network mocked) ----------------
class FakeResp:
    def __init__(self, status, data):
        self.status_code, self._d = status, data
        self.text = str(data)

    def json(self):
        return self._d


def _ok(text):
    return FakeResp(200, {"candidates": [{"content": {"parts": [{"text": "thinking", "thought": True}, {"text": text}]}}]})


@pytest.fixture
def gemini(monkeypatch):
    from app.settings import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "test-key")
    monkeypatch.setattr(s, "gemini_text_models", "m1,m2")
    monkeypatch.setattr(s, "gemini_asr_models", "m1")
    calls = []

    def install(responses):
        def fake_post(url, json=None, timeout=None, headers=None):
            calls.append(url.split("/models/")[1].split(":")[0])
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        monkeypatch.setattr(httpx, "post", fake_post)
        return calls
    return install


def test_gemini_falls_back_to_next_model_when_overloaded(gemini):
    from app.ai.providers.gemini import GeminiLLM
    calls = gemini([FakeResp(503, {"error": {"message": "high demand"}}), _ok('```json\n{"task": "tile"}\n```')])
    assert GeminiLLM().complete_json(task="extract_job", system="s", prompt="{}", schema={}) == {"task": "tile"}
    assert calls == ["m1", "m2"]


def test_gemini_extraction_numbers_still_grounded(gemini):
    from app.ai import extraction
    from app.ai.chain import Chain
    from app.ai.providers.gemini import GeminiLLM
    from app.country_config import get_country
    gemini([_ok('{"task": "tile", "headcount": 4, "daily_rate": 9999, "location_text": "G-13"}')])
    ex = extraction.extract("chaar mazdoor G-13 tile 1500", get_country("PK"), Chain("llm", [GeminiLLM()]), "ur")
    assert ex.provider == "gemini" and ex.fields["task"] == "tile"
    assert ex.fields["daily_rate"] is None and "daily_rate" in ex.uncertain   # invented number dropped


def test_gemini_asr_converts_hindi_script_to_urdu(gemini):
    from app.ai.providers.gemini import GeminiASR
    gemini([_ok("यह काम जी तेरा में है"), _ok("یہ کام جی تیرہ میں ہے")])
    assert GeminiASR().transcribe(b"RIFF....", "audio/webm;codecs=opus", "ur").text == "یہ کام جی تیرہ میں ہے"


def test_gemini_tts_wraps_pcm_as_wav(gemini):
    from app.ai.providers.gemini import GeminiTTS
    pcm = b"\x01\x00" * 100
    gemini([FakeResp(200, {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/L16;codec=pcm;rate=24000",
                                                                               "data": base64.b64encode(pcm).decode()}}]}}]})])
    a = GeminiTTS().synthesize("salam", "ur")
    assert a.mime == "audio/wav" and a.data[:4] == b"RIFF" and a.data.endswith(pcm)


def test_gemini_without_key_fails_fast_so_chain_uses_mock(monkeypatch):
    from app.ai.chain import Chain
    from app.ai.mock import MockLLM
    from app.ai.providers.gemini import GeminiLLM
    from app.settings import get_settings
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    _, used = Chain("llm", [GeminiLLM(), MockLLM("mock-a", "mock-a")]).call(
        "complete_json", task="verify_readback", system="", prompt='{"readback": "x", "fields": {}}', schema={})
    assert used == "mock-a"
