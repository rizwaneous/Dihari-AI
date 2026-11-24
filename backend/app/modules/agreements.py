"""Selecting workers → immutable agreement snapshot visible to both parties."""
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import Agreement, Assignment, Job, JobStatus as S, Offer, User
from . import audit, jobs
from .notifications import notify


class AgreementError(Exception):
    def __init__(self, code: str, detail=None):
        super().__init__(code)
        self.code, self.detail = code, detail


def build_terms(job: Job, rate: int) -> dict:
    return {"job_id": job.id, "task": job.task, "location_text": job.location_text,
            "address_detail": job.address_detail, "lat": job.lat, "lon": job.lon,
            "start_at": job.start_at.isoformat(), "days": job.days, "daily_rate": rate,
            "posted_rate": job.daily_rate, "hours_per_day": job.hours_per_day,
            "payment_day": job.payment_day.isoformat(), "advance": job.advance, "deductions": job.deductions,
            "transport_mode": job.transport_mode, "transport_amount": job.transport_amount,
            "currency_country": job.country_code, "rule_version": job.rule_version, "rule_verified": job.rule_verified}


def terms_hash(terms: dict) -> str:
    return hashlib.sha256(json.dumps(terms, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def select_workers(db: Session, job: Job, hirer: User, offer_ids: list[str], *, direct=False) -> list[Assignment]:
    if job.hirer_id != hirer.id:
        raise AgreementError("forbidden")
    taken = jobs.lock_for_booking(db, job)
    if job.start_at < utcnow():
        raise AgreementError("job_expired")
    if job.flagged or job.status not in (S.offers.value, S.assigned.value):
        raise AgreementError("job_not_open_for_selection")
    if taken + len(offer_ids) > job.headcount:
        raise AgreementError("exceeds_headcount", {"headcount": job.headcount, "taken": taken})
    out = []
    for oid in offer_ids:
        o = db.get(Offer, oid)
        if not o or o.job_id != job.id or o.status != "pending":
            raise AgreementError("bad_offer", oid)
        terms = build_terms(job, o.rate)
        ag = Agreement(job_id=job.id, worker_id=o.worker_id, hirer_id=job.hirer_id, terms=terms, terms_hash=terms_hash(terms))
        db.add(ag)
        db.flush()
        asg = db.scalar(select(Assignment).where(Assignment.job_id == job.id, Assignment.worker_id == o.worker_id))
        if asg is None:
            asg = Assignment(job_id=job.id, worker_id=o.worker_id)
        elif asg.status != "cancelled":
            raise AgreementError("already_selected")
        asg.agreement_id = ag.id
        asg.status = "confirmed" if direct else "assigned"
        asg.worker_confirmed_at = utcnow() if direct else None
        db.add(asg)
        o.status = "selected"
        audit.log(db, hirer.id, "agreement", ag.id, "created", data={"worker": o.worker_id, "rate": o.rate, "hash": ag.terms_hash})
        notify(db, o.worker_id, "booked" if direct else "assigned", job.id)
        if direct:
            notify(db, job.hirer_id, "worker_confirmed", job.id)
        out.append(asg)
    if job.headcount == taken + len(offer_ids):  # all seats filled: close remaining offers
        for o in db.scalars(select(Offer).where(Offer.job_id == job.id, Offer.status == "pending")):
            o.status = "rejected"
    jobs.transition(db, job, S.assigned, hirer.id, {"selected": len(offer_ids)})
    db.commit()
    return out


def worker_confirm(db: Session, asg: Assignment, worker: User) -> Assignment:
    if asg.worker_id != worker.id:
        raise AgreementError("forbidden")
    job = db.get(Job, asg.job_id)
    jobs.lock_for_booking(db, job)
    db.refresh(asg)
    if asg.status != "assigned" or job.status != S.assigned.value:
        raise AgreementError("bad_state", asg.status)
    asg.status, asg.worker_confirmed_at = "confirmed", utcnow()
    audit.log(db, worker.id, "assignment", asg.id, "confirmed", "assigned", "confirmed")
    notify(db, job.hirer_id, "worker_confirmed", job.id)
    db.commit()
    return asg


def worker_cancel(db: Session, asg: Assignment, worker: User) -> Assignment:
    if asg.worker_id != worker.id or asg.status not in ("assigned", "confirmed"):
        raise AgreementError("forbidden")
    job = db.get(Job, asg.job_id)
    jobs.lock_for_booking(db, job)
    db.refresh(asg)
    if job.status != S.assigned.value or asg.status not in ("assigned", "confirmed"):
        raise AgreementError("too_late")
    audit.log(db, worker.id, "assignment", asg.id, "cancelled", asg.status, "cancelled")
    asg.status = "cancelled"
    offer = db.scalar(select(Offer).where(Offer.job_id == job.id, Offer.worker_id == worker.id))
    if offer:
        offer.status = "withdrawn"
    notify(db, job.hirer_id, "worker_cancelled", job.id)
    db.commit()
    return asg
