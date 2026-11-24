"""Offers and counter-offers. Counter must be strictly HIGHER than the posted rate (enforced here)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..country_config import get_country
from ..db import utcnow
from ..models import Job, JobStatus as S, Offer, User
from . import audit, jobs


class OfferError(Exception):
    def __init__(self, code: str, detail=None):
        super().__init__(code)
        self.code, self.detail = code, detail


def make_offer(db: Session, job: Job, worker: User, rate: int | None = None, *, commit=True) -> Offer:
    """rate None → accept at the posted rate. Otherwise a counter that must be > job.daily_rate."""
    if worker.role != "worker":
        raise OfferError("not_worker")
    if job.hirer_id == worker.id:
        raise OfferError("own_job")
    taken = jobs.lock_for_booking(db, job)
    if job.start_at < utcnow():
        raise OfferError("job_expired")
    if taken >= job.headcount or job.status not in (S.open.value, S.offers.value, S.assigned.value):
        raise OfferError("job_closed")
    if job.flagged:
        raise OfferError("job_flagged")
    cfg = get_country(job.country_code)
    kind = "accept"
    if rate is None or rate == job.daily_rate:
        rate = job.daily_rate
    else:
        if rate < job.daily_rate:
            raise OfferError("counter_must_be_higher", {"offered": job.daily_rate})
        cap = int(job.daily_rate * cfg.max_counter_multiple)
        if rate > cap:
            raise OfferError("counter_too_high", {"max": cap})
        kind = "counter"
    existing = db.scalars(select(Offer).where(Offer.job_id == job.id, Offer.worker_id == worker.id)).first()
    if existing and existing.status == "selected":
        raise OfferError("already_selected")
    if existing:
        existing.rate, existing.kind, existing.status = rate, kind, "pending"
        offer = existing
    else:
        offer = Offer(job_id=job.id, worker_id=worker.id, rate=rate, kind=kind)
        db.add(offer)
        db.flush()
    if job.status == S.open.value:
        jobs.transition(db, job, S.offers, worker.id)
    audit.log(db, worker.id, "offer", offer.id, kind, data={"job": job.id, "rate": rate})
    if commit:
        from .notifications import notify
        notify(db, job.hirer_id, "new_offer", job.id)
        db.commit()
    else:
        db.flush()
    return offer


def withdraw(db: Session, offer: Offer, worker: User) -> Offer:
    if offer.worker_id != worker.id:
        raise OfferError("forbidden")
    if offer.status == "selected":
        raise OfferError("already_selected")
    offer.status = "withdrawn"
    audit.log(db, worker.id, "offer", offer.id, "withdrawn")
    if commit:
        from .notifications import notify
        notify(db, job.hirer_id, "new_offer", job.id)
        db.commit()
    else:
        db.flush()
    return offer
