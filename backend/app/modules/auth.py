from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..country_config import registry
from ..db import utcnow
from ..models import OtpCode, User
from ..security import hash_code, make_token, new_otp
from ..settings import get_settings
from . import audit
from .abuse import limiter
from .notifications import get_sms


class AuthError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def request_otp(db: Session, raw_phone: str, country: str | None = None) -> dict:
    reg = registry()
    if country:
        cfg = reg.get(country)
        phone = cfg.normalize_phone(raw_phone)
    else:
        found = reg.detect_by_phone(raw_phone)
        cfg, phone = found if found else (None, None)
    if not phone:
        raise AuthError("invalid_phone")
    limiter.check(f"otp:{phone}", 3, 600)
    code = new_otp()
    db.add(OtpCode(phone=phone, code_hash=hash_code(f"{phone}:{code}"),
                   expires_at=utcnow() + timedelta(seconds=get_settings().otp_ttl_seconds)))
    sms = get_sms()
    if not sms.send(phone, f"Dihari code: {code}"):
        db.rollback()
        raise AuthError("sms_unavailable")
    db.commit()
    out = {"phone": phone, "country": cfg.code}
    if get_settings().dev_mode and sms.name == "stub":
        out["dev_otp"] = code
    return out


def verify_otp(db: Session, raw_phone: str, code: str, role: str | None = None, locale: str | None = None) -> dict:
    found = registry().detect_by_phone(raw_phone)
    if not found:
        raise AuthError("invalid_phone")
    cfg, phone = found
    row = db.scalars(select(OtpCode).where(OtpCode.phone == phone, OtpCode.consumed == False)  # noqa: E712
                     .order_by(OtpCode.created_at.desc())).first()
    if not row or row.expires_at < utcnow():
        raise AuthError("otp_expired")
    if row.attempts >= get_settings().otp_max_attempts:
        raise AuthError("otp_locked")
    row.attempts += 1
    if row.code_hash != hash_code(f"{phone}:{code}"):
        db.commit()
        raise AuthError("otp_wrong")
    row.consumed = True
    user = db.scalars(select(User).where(User.phone == phone)).first()
    created = user is None
    if created:
        user = User(phone=phone, country_code=cfg.code, role=role or "worker",
                    locale=locale or cfg.default_language, phone_verified=True)
        db.add(user)
        db.flush()
        audit.log(db, user.id, "user", user.id, "created", data={"role": user.role})
    else:
        if user.suspended:
            raise AuthError("suspended")
        user.phone_verified = True
        if role and user.role != role:
            user.role = role
    db.commit()
    return {"token": make_token(user.id), "user_id": user.id, "role": user.role, "is_new": created}
