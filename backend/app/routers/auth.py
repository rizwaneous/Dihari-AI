from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..modules import auth
from ..modules.abuse import RateLimited

router = APIRouter(prefix="/auth", tags=["auth"])


class OtpReq(BaseModel):
    phone: str
    country: str | None = None


class OtpVerify(BaseModel):
    phone: str
    code: str
    role: str | None = None
    locale: str | None = None


@router.post("/request-otp")
def request_otp(body: OtpReq, db: Session = Depends(get_db)):
    try:
        return auth.request_otp(db, body.phone, body.country)
    except auth.AuthError as e:
        raise HTTPException(503 if e.code == "sms_unavailable" else 400, e.code)
    except RateLimited as e:
        raise HTTPException(429, "rate_limited", headers={"Retry-After": str(e.retry_after)})


@router.post("/verify-otp")
def verify_otp(body: OtpVerify, db: Session = Depends(get_db)):
    if body.role not in (None, "worker", "hirer"):
        raise HTTPException(400, "invalid_role")
    try:
        return auth.verify_otp(db, body.phone, body.code, body.role, body.locale)
    except auth.AuthError as e:
        raise HTTPException(400 if e.code != "suspended" else 403, e.code)


# ---- Demo accounts (prototype only). Active only while DEV_MODE=true and DEMO_LOGINS=true. ----
from ..settings import get_settings  # noqa: E402


class DemoLogin(BaseModel):
    role: str


def _demo_enabled() -> bool:
    s = get_settings()
    return s.dev_mode and s.demo_logins


@router.get("/demo")
def demo_accounts(db: Session = Depends(get_db)):
    if not _demo_enabled():
        return {"enabled": False, "accounts": []}
    from ..modules import demo
    return {"enabled": True, "accounts": demo.accounts(db)}


@router.post("/demo-login")
def demo_login(body: DemoLogin, db: Session = Depends(get_db)):
    if not _demo_enabled():
        raise HTTPException(404)
    if body.role not in ("worker", "hirer"):
        raise HTTPException(400, "invalid_role")
    from ..modules import demo
    from ..security import make_token
    user = demo.ensure(db)[body.role]
    return {"token": make_token(user.id), "user_id": user.id, "role": user.role}
