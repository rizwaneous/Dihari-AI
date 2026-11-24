"""Serialisers. Privacy rules live here: exact location only for the hirer and assigned workers."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .country_config import get_country
from .db import utcnow
from .models import Assignment, HirerProfile, Job, Offer, User, WorkerProfile
from .modules import geo, reputation
from .modules.jobs import booked_count


def job_view(db: Session, job: Job, viewer: User, *, from_lat=None, from_lon=None) -> dict:
    cfg = get_country(job.country_code)
    is_owner = job.hirer_id == viewer.id
    asg = db.scalars(select(Assignment).where(Assignment.job_id == job.id, Assignment.worker_id == viewer.id,
                                              Assignment.status.in_(["assigned", "confirmed", "completed"]))).first()
    exact = is_owner or asg is not None
    lat, lon = (job.lat, job.lon) if exact else geo.fuzz_location(job.id, job.lat, job.lon)
    trade = cfg.trade(job.task)
    v = {"id": job.id, "status": job.status, "task": job.task, "task_icon": trade.icon if trade else "🛠️",
         "task_name": (trade.names if trade else {}).get(viewer.locale) or job.task,
         "headcount": job.headcount, "location_text": job.location_text, "region": job.region,
         "lat": lat, "lon": lon, "location_exact": exact, "start_at": job.start_at.isoformat(), "days": job.days,
         "daily_rate": job.daily_rate, "hours_per_day": job.hours_per_day, "payment_day": job.payment_day.isoformat(),
         "advance": job.advance, "deductions": job.deductions, "transport_mode": job.transport_mode,
         "transport_amount": job.transport_amount, "currency": cfg.currency.code, "rule_verified": job.rule_verified,
         "readback_verified": job.readback_verified, "hirer_reputation": reputation.hirer_reputation(db, job.hirer_id)}
    v["booked"] = db.scalar(select(booked_count()).select_from(Job).where(Job.id == job.id))
    v["booking_expired"] = job.start_at < utcnow() and job.status in ("open", "offers", "assigned")
    if exact:
        v["address_detail"] = job.address_detail
    if from_lat is not None and from_lon is not None:
        v["distance_km"] = round(round(geo.haversine_m(from_lat, from_lon, job.lat, job.lon) / 500) * 0.5, 1)
    if viewer.role == "worker":
        o = db.scalars(select(Offer).where(Offer.job_id == job.id, Offer.worker_id == viewer.id)).first()
        v["my_offer"] = o and {"id": o.id, "rate": o.rate, "kind": o.kind, "status": o.status}
        v["my_assignment_id"] = asg.id if asg else None
    return v


def worker_card(db: Session, w: User, job: Job, offer: Offer | None = None) -> dict:
    """What a hirer sees about a worker: first name + reputation. Never phone before assignment."""
    wp = db.get(WorkerProfile, w.id)
    rep = reputation.worker_reputation(db, w.id)
    d = {"worker_id": w.id, "first_name": reputation.first_name(w), **rep}
    if wp and wp.lat is not None:
        d["distance_km"] = round(geo.haversine_m(wp.lat, wp.lon, job.lat, job.lon) / 1000, 1)
    if offer:
        d.update(offer_id=offer.id, rate=offer.rate, kind=offer.kind)
    return d


def rank_offers(db: Session, job: Job, sort: str = "best") -> list[dict]:
    offs = db.scalars(select(Offer).where(Offer.job_id == job.id, Offer.status.in_(["pending", "selected"]))).all()
    cards = [worker_card(db, db.get(User, o.worker_id), job, o) | {"status": o.status} for o in offs]
    if not cards:
        return []
    rates = [c["rate"] for c in cards]
    lo, hi = min(rates), max(rates)
    dmax = max([c.get("distance_km", 0) for c in cards] + [1])
    for c in cards:
        price = 1 - (c["rate"] - lo) / (hi - lo) if hi > lo else 1
        dist = 1 - c.get("distance_km", dmax) / dmax
        rating = (c["avg_rating"] or 3) / 5
        rel = c["completion_rate"] if c["completion_rate"] is not None else 0.7
        c["score"] = round(0.25 * dist + 0.25 * price + 0.2 * rating + 0.3 * rel + c["tier"]["boost"], 4)
    key = {"best": lambda c: -c["score"], "distance": lambda c: c.get("distance_km", 1e9),
           "price": lambda c: c["rate"], "rating": lambda c: -(c["avg_rating"] or 0),
           "reliability": lambda c: -(c["completion_rate"] or 0)}[sort]
    return sorted(cards, key=key)
