from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import numbers as nm, pipeline, readback, service
from ..ai.base import AIUnavailable
from ..country_config import get_country
from ..db import get_db
from ..deps import current_user
from ..models import Agreement, Job, User
from ..modules.abuse import RateLimited, limiter
from ..settings import get_settings

router = APIRouter(tags=["voice"])


class DraftIn(BaseModel):
    transcript: str
    fields: dict | None = None
    lang: str | None = None
    now: datetime | None = None   # dev-only override


class AnswerIn(BaseModel):
    field: str
    transcript: str
    fields: dict
    lang: str | None = None
    now: datetime | None = None


class FieldsIn(BaseModel):
    fields: dict
    lang: str | None = None


class TtsIn(BaseModel):
    text: str
    lang: str = "ur"


class CommandIn(BaseModel):
    transcript: str
    lang: str | None = None


class IntentIn(BaseModel):
    transcript: str
    lang: str | None = None


def _now(n):
    return n if (n and get_settings().dev_mode) else datetime.now(timezone.utc)


def _limit(user: User, n=30):
    try:
        limiter.check(f"voice:{user.id}", n, 60)
    except RateLimited as e:
        raise HTTPException(429, "rate_limited", headers={"Retry-After": str(e.retry_after)})


@router.get("/ai/capabilities")
def capabilities():
    out = {}
    for k in ("asr", "tts"):
        ch = service.get_chain(k)
        out[k] = {"available": bool(ch.providers), "real": ch.has_real}
    out["llm"] = {"real": service.get_chain("extract").has_real}
    return out


@router.post("/ai/transcribe")
async def transcribe(audio: UploadFile = File(...), lang: str = Form("ur"), user: User = Depends(current_user)):
    _limit(user, 20)
    data = await audio.read()
    if len(data) > 5_000_000:
        raise HTTPException(413, "audio too large")
    try:
        tr, _ = service.get_chain("asr").call("transcribe", data, audio.content_type or "audio/webm", lang)
    except AIUnavailable as e:
        raise HTTPException(503, {"degraded": True, "reason": str(e)})
    return {"text": tr.text, "confidence": tr.confidence, "provider": tr.provider}


@router.post("/ai/tts")
def tts(body: TtsIn, user: User = Depends(current_user)):
    _limit(user, 60)
    try:
        a, _ = service.get_chain("tts").call("synthesize", body.text[:600], body.lang)
    except AIUnavailable as e:
        raise HTTPException(503, {"degraded": True, "reason": str(e)})
    return Response(a.data, media_type=a.mime, headers={"X-TTS-Provider": a.provider})


@router.post("/voice/draft")
def draft(body: DraftIn, user: User = Depends(current_user)):
    _limit(user)
    cfg, lang = get_country(user.country_code), body.lang or user.locale
    return pipeline.draft_from_text(body.transcript, cfg, lang, body.fields, _now(body.now))


@router.post("/voice/answer")
def answer(body: AnswerIn, user: User = Depends(current_user)):
    _limit(user)
    cfg, lang = get_country(user.country_code), body.lang or user.locale
    return pipeline.draft_from_answer(body.field, body.transcript, body.fields, cfg, lang, _now(body.now))


@router.post("/voice/validate")
def validate(body: FieldsIn, user: User = Depends(current_user)):
    """Tap-only path: works with no ASR/LLM configured."""
    cfg, lang = get_country(user.country_code), body.lang or user.locale
    return pipeline.draft_from_fields(body.fields, cfg, lang)


@router.post("/voice/intent")
def intent(body: IntentIn, user: User = Depends(current_user)):
    return {"intent": nm.yes_no(body.transcript, body.lang or user.locale)}


@router.get("/jobs/{job_id}/readback")
def job_readback(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404)
    cfg = get_country(j.country_code)
    f = dict(task=j.task, headcount=j.headcount, location_text=j.location_text, start_at=j.start_at, days=j.days,
             daily_rate=j.daily_rate, hours_per_day=j.hours_per_day, payment_day=j.payment_day, advance=j.advance,
             deductions=j.deductions, transport_mode=j.transport_mode, transport_amount=j.transport_amount)
    return {"text": readback.render(f, cfg, user.locale, datetime.now(timezone.utc))}


@router.get("/agreements/{agreement_id}/readback")
def agreement_readback(agreement_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ag = db.get(Agreement, agreement_id)
    if not ag or user.id not in (ag.worker_id, ag.hirer_id):
        raise HTTPException(404)
    t = ag.terms
    cfg = get_country(t["currency_country"])
    j = db.get(Job, ag.job_id)
    f = dict(t, headcount=j.headcount)
    return {"text": readback.render(f, cfg, user.locale, datetime.now(timezone.utc))}


@router.post("/voice/command")
def command(body: CommandIn, user: User = Depends(current_user)):
    """Spoken navigation: returns which screen/action to open and a sentence to say back."""
    from ..ai import commands
    _limit(user)
    lang = body.lang or user.locale
    return commands.route(body.transcript[:500], user.role, get_country(user.country_code), lang, service.get_chain("extract"))
