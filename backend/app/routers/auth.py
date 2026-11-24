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
