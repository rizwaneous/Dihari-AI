from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, need_role
from ..models import Agreement, Assignment, Case, Job, User
from ..modules import agreements, cases, payments, reputation
from ..settings import get_settings
from ..views import job_view

router = APIRouter(tags=["agreements"])


class PayIn(BaseModel):
    status: str


class RateIn(BaseModel):
    stars: int


def _asg(db, asg_id) -> Assignment:
    a = db.get(Assignment, asg_id)
    if not a:
        raise HTTPException(404)
    return a


def _e(e, status=409):
    return HTTPException(status, {"code": getattr(e, "code", str(e)), "detail": getattr(e, "detail", None)})


@router.get("/my/work")
def my_work(user: User = Depends(need_role("worker")), db: Session = Depends(get_db)):
    out = []
    for a in db.scalars(select(Assignment).where(Assignment.worker_id == user.id)):
        j, ag = db.get(Job, a.job_id), db.get(Agreement, a.agreement_id)
        out.append({"assignment_id": a.id, "agreement_id": a.agreement_id, "status": a.status, "job": job_view(db, j, user), "terms": ag.terms,
                    "terms_hash": ag.terms_hash, "payment_report": a.payment_report, "job_status": j.status,
                    "payment_day": j.payment_day.isoformat()})
    return out


@router.get("/my/stats")
def my_stats(user: User = Depends(need_role("worker")), db: Session = Depends(get_db)):
    """Earnings, tier progress and the Kaam Card (verified work history)."""
    return reputation.worker_stats(db, user.id)


@router.get("/agreements/{agreement_id}")
def get_agreement(agreement_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ag = db.get(Agreement, agreement_id)
    if not ag or user.id not in (ag.worker_id, ag.hirer_id):
        raise HTTPException(404)
    asg = db.scalars(select(Assignment).where(Assignment.agreement_id == ag.id)).first()
    w = db.get(User, ag.worker_id)
    return {"id": ag.id, "terms": ag.terms, "terms_hash": ag.terms_hash, "created_at": ag.created_at.isoformat(),
            "assignment_id": asg.id, "assignment_status": asg.status,
            "worker": {"first_name": reputation.first_name(w), "phone": w.phone} if user.id == ag.hirer_id else None,
            "hirer": {"first_name": reputation.first_name(db.get(User, ag.hirer_id)), "phone": db.get(User, ag.hirer_id).phone}
            if user.id == ag.worker_id else None}


@router.post("/assignments/{asg_id}/confirm")
def confirm(asg_id: str, user: User = Depends(need_role("worker")), db: Session = Depends(get_db)):
    try:
        a = agreements.worker_confirm(db, _asg(db, asg_id), user)
    except agreements.AgreementError as e:
        raise _e(e, 403 if e.code == "forbidden" else 409)
    return {"status": a.status}


@router.post("/assignments/{asg_id}/cancel")
def cancel(asg_id: str, user: User = Depends(need_role("worker")), db: Session = Depends(get_db)):
    try:
        a = agreements.worker_cancel(db, _asg(db, asg_id), user)
    except agreements.AgreementError as e:
        raise _e(e)
    return {"status": a.status}


@router.post("/assignments/{asg_id}/payment")
def worker_payment(asg_id: str, body: PayIn, user: User = Depends(need_role("worker")), db: Session = Depends(get_db)):
    try:
        a = payments.report_payment(db, _asg(db, asg_id), user, body.status)
    except payments.PaymentError as e:
        raise _e(e, 403 if e.code == "forbidden" else 409)
    return {"payment_report": a.payment_report}


@router.post("/assignments/{asg_id}/hirer-payment")
def hirer_payment(asg_id: str, body: PayIn, user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    try:
        a = payments.hirer_claim(db, _asg(db, asg_id), user, body.status)
    except payments.PaymentError as e:
        raise _e(e, 403 if e.code == "forbidden" else 409)
    return {"hirer_payment_claim": a.hirer_payment_claim}


@router.post("/assignments/{asg_id}/rate")
def rate(asg_id: str, body: RateIn, user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    try:
        payments.rate_worker(db, _asg(db, asg_id), user, body.stars)
    except payments.PaymentError as e:
        raise _e(e)
    return {"ok": True}


@router.get("/my/cases")
def my_cases(user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    """Hirer-facing case list: worker identity is never included."""
    return [cases.hirer_view(db, c) for c in db.scalars(select(Case).where(Case.hirer_id == user.id))]


@router.get("/reputation/{user_id}")
def rep(user_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404)
    return reputation.hirer_reputation(db, user_id) if target.role == "hirer" else reputation.worker_reputation(db, user_id)


@router.post("/dev/tick")
def dev_tick(now: datetime | None = None, db: Session = Depends(get_db)):
    """Run scheduled reminders. `now` override is dev-mode only (used by the demo to jump a week ahead)."""
    s = get_settings()
    if now is not None and not s.dev_mode:
        raise HTTPException(403, "now override is dev-only")
    return {"reminders_sent": payments.send_due_reminders(db, now)}


@router.post("/dev/advance-days")
def dev_advance(days: int = 7):
    """DEV_MODE only: move the server clock forward (demo: 'a week later')."""
    from datetime import timedelta
    from ..db import CLOCK
    if not get_settings().dev_mode:
        raise HTTPException(403, "dev only")
    CLOCK.offset += timedelta(days=days)
    return {"offset_days": CLOCK.offset.days}


@router.post("/dev/reset-clock")
def dev_reset():
    from datetime import timedelta
    from ..db import CLOCK
    if not get_settings().dev_mode:
        raise HTTPException(403, "dev only")
    CLOCK.offset = timedelta(0)
    return {"offset_days": 0}
