"""Job lifecycle: strict state machine. Illegal transitions raise."""
from datetime import date, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..country_config import get_country
from ..db import utcnow
from ..models import Assignment, HirerProfile, Job, JobStatus as S, User
from ..settings import get_settings
from . import audit, wage_floor
from .abuse import limiter


class IllegalTransition(Exception):
    pass


class JobRejected(Exception):
    """Job cannot be created (wage floor, abuse limits, ...)."""
    def __init__(self, code: str, detail=None):
        super().__init__(code)
        self.code, self.detail = code, detail


TRANSITIONS: dict[S, set[S]] = {
    S.open: {S.offers, S.assigned, S.cancelled},
    S.offers: {S.offers, S.assigned, S.cancelled},
    S.assigned: {S.assigned, S.in_progress, S.cancelled},
    S.in_progress: {S.completed},
    S.completed: {S.payment_confirmed, S.disputed},
    S.payment_confirmed: set(),
    S.disputed: {S.payment_confirmed},   # a human-reviewed case may later resolve as paid
    S.cancelled: set(),
}


def transition(db: Session, job: Job, to: S, actor: str, data: dict | None = None) -> Job:
    frm = S(job.status)
    if to not in TRANSITIONS[frm] or (to == frm and frm not in (S.offers, S.assigned)):
        raise IllegalTransition(f"{frm.value} -> {to.value}")
    job.status = to.value
    audit.log(db, actor, "job", job.id, "transition", frm.value, to.value, data)
    return job


def booked_count():
    return (select(func.count(Assignment.id)).where(
        Assignment.job_id == Job.id, Assignment.status != "cancelled"
    ).correlate(Job).scalar_subquery())


def lock_for_booking(db: Session, job: Job) -> int:
    # A write takes a per-job lock on Postgres and serializes writers on SQLite.
    db.execute(update(Job).where(Job.id == job.id).values(status=Job.status))
    db.refresh(job)
    return db.scalar(select(booked_count()).select_from(Job).where(Job.id == job.id))


REQUIRED = ["task", "headcount", "location_text", "start_at", "daily_rate", "hours_per_day", "payment_day"]


def create_job(db: Session, hirer: User, f: dict, *, readback_verified: bool = False,
               transcript: str | None = None, on: date | None = None) -> Job:
    """f: validated field dict. Wage floor re-run server-side; nothing the client says is trusted."""
    cfg = get_country(hirer.country_code)
    s = get_settings()
    missing = [k for k in REQUIRED if f.get(k) in (None, "")]
    if missing:
        raise JobRejected("missing_fields", missing)
    hp = db.get(HirerProfile, hirer.id)
    if hp and hp.posting_restricted:
        raise JobRejected("posting_restricted")
    from .abuse import RateLimited
    try:
        limiter.check(f"post:{hirer.id}", s.max_posts_per_hirer_per_hour, 3600)
    except RateLimited:
        raise JobRejected("rate_limited")
    day_ago = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    n_today = db.scalar(select(func.count()).select_from(Job).where(Job.hirer_id == hirer.id, Job.created_at >= day_ago))
    if n_today >= s.max_jobs_per_hirer_per_day:
        raise JobRejected("daily_limit")
    n_open = db.scalar(select(func.count()).select_from(Job).where(
        Job.hirer_id == hirer.id, Job.start_at >= utcnow(), booked_count() < Job.headcount,
        Job.status.in_([S.open.value, S.offers.value, S.assigned.value])))
    if n_open >= s.max_open_jobs_per_hirer:
        raise JobRejected("too_many_open")

    start_at: datetime = f["start_at"]
    place = cfg.find_place(f["location_text"])
    lat = f.get("lat") if f.get("lat") is not None else (place.lat if place else None)
    lon = f.get("lon") if f.get("lon") is not None else (place.lon if place else None)
    if lat is None or lon is None:
        raise JobRejected("location_unresolved")
    region = cfg.resolve_region(f["location_text"], lat, lon)
    payment_day = f["payment_day"]
    days = int(f.get("days") or 1)
    ded = f.get("deductions") or []
    chk = wage_floor.check(country=cfg.code, region=region, daily_rate=int(f["daily_rate"]),
                           hours_per_day=float(f["hours_per_day"]), payment_day=payment_day,
                           start_date=start_at.date(), days=days, deductions=ded, on=on or date.today())
    if not chk.ok:
        raise JobRejected("wage_floor", chk.to_dict(hirer.locale))

    dup = db.scalar(select(func.count()).select_from(Job).where(
        Job.hirer_id == hirer.id, Job.task == f["task"], Job.location_text == f["location_text"],
        Job.daily_rate == int(f["daily_rate"]),
        Job.start_at.between(start_at - timedelta(hours=1), start_at + timedelta(hours=1)),
        Job.status.in_([S.open.value, S.offers.value])))
    if dup:
        raise JobRejected("duplicate")

    job = Job(hirer_id=hirer.id, country_code=cfg.code, region=region, task=f["task"],
              headcount=int(f["headcount"]), location_text=f["location_text"], address_detail=f.get("address_detail"),
              lat=lat, lon=lon, start_at=start_at, days=days, daily_rate=int(f["daily_rate"]),
              hours_per_day=float(f["hours_per_day"]), payment_day=payment_day, advance=int(f.get("advance") or 0),
              deductions=ded, transport_mode=f.get("transport_mode") or "none",
              transport_amount=f.get("transport_amount"), transcript=transcript, readback_verified=readback_verified,
              rule_version=chk.rule.version, rule_verified=chk.rule.verified)
    db.add(job)
    db.flush()
    audit.log(db, hirer.id, "job", job.id, "created", None, S.open.value,
              {"rate": job.daily_rate, "rule": chk.rule.version, "rule_verified": chk.rule.verified})
    from .geo import nearby_workers
    from .notifications import notify
    for worker, profile, dist in nearby_workers(db, lat, lon, cfg.max_radius_km, country=cfg.code,
                                               trade=job.task, limit=None):
        if dist <= (profile.radius_km or cfg.default_radius_km) * 1000:
            notify(db, worker.id, "nearby_job", job.id)
    db.commit()
    return job
