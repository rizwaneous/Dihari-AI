"""Prototype demo accounts: one hirer, one labourer, one tap to log in and switch.

`ensure(db)` is idempotent. It creates (or tidies) the two accounts and gives the labourer a short, believable
work history so the tier badge, earnings and Kaam Card have something to show. History jobs are marked with
transcript="demo-history" and are in the past, so they never appear in the live job feed.
Only reachable while DEV_MODE=true and DEMO_LOGINS=true (see routers/auth.py)."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..country_config import get_country
from ..models import Agreement, Assignment, HirerProfile, Job, JobStatus as S, User, WorkerProfile
from ..settings import get_settings
from . import agreements as ag

HISTORY_MARK = "demo-history"
# (trade, days ago, days, rate, stars, history hirer index)
HISTORY = [("mason", 52, 2, 1700, 5, 0), ("tile", 40, 1, 1600, 4, 1), ("labour", 33, 1, 1200, 5, 2),
           ("mason", 26, 3, 1750, 5, 0), ("paint", 18, 1, 1500, 4, 3), ("tile", 11, 2, 1650, 5, 1),
           ("labour", 5, 1, 1250, 5, 2)]
HISTORY_HIRERS = ["Sana Malik", "Tariq Builders", "Rubina Bibi", "Zahid Constructions"]


def _user(db: Session, raw_phone: str, role: str, name: str) -> User:
    cfg = get_country()
    phone = cfg.normalize_phone(raw_phone)
    u = db.scalar(select(User).where(User.phone == phone))
    if u is None:
        u = User(phone=phone, country_code=cfg.code, role=role, locale=cfg.default_language, name=name, phone_verified=True)
        db.add(u)
        db.flush()
    return u


def ensure(db: Session) -> dict[str, User]:
    s, cfg = get_settings(), get_country()
    hirer = _user(db, s.demo_hirer_phone, "hirer", "Kamran Thekedar")
    worker = _user(db, s.demo_worker_phone, "worker", "Ali Khan")
    hirer.role, worker.role = "hirer", "worker"
    if not db.get(HirerProfile, hirer.id):
        db.add(HirerProfile(user_id=hirer.id, hirer_type="contractor"))
    wp = db.get(WorkerProfile, worker.id)
    home = cfg.places[0]
    if wp is None:
        wp = WorkerProfile(user_id=worker.id)
        db.add(wp)
    wp.trades = [t.code for t in cfg.trades]          # demo labourer sees every trade
    if wp.lat is None:
        wp.area_name, wp.lat, wp.lon = home.name, home.lat, home.lon
    wp.radius_km = max(wp.radius_km or 0, cfg.max_radius_km)
    db.flush()
    _history(db, worker, cfg)
    db.commit()
    return {"hirer": hirer, "worker": worker}


def _history(db: Session, worker: User, cfg) -> None:
    done = db.scalar(select(Assignment.id).join(Job, Job.id == Assignment.job_id)
                     .where(Assignment.worker_id == worker.id, Job.transcript == HISTORY_MARK))
    if done:
        return
    hirers = [_user(db, f"0300{3000000 + i:07d}", "hirer", n) for i, n in enumerate(HISTORY_HIRERS)]
    now = datetime.now(timezone.utc)
    for i, (trade, ago, days, rate, stars, hi) in enumerate(HISTORY):
        if not cfg.trade(trade):
            continue
        place = cfg.places[i % len(cfg.places)]
        start = (now - timedelta(days=ago)).replace(hour=3, minute=0, second=0, microsecond=0)
        job = Job(hirer_id=hirers[hi].id, country_code=cfg.code, region=cfg.resolve_region(place.name, place.lat, place.lon),
                  status=S.payment_confirmed.value, task=trade, headcount=1, location_text=place.name, lat=place.lat,
                  lon=place.lon, start_at=start, days=days, daily_rate=rate, hours_per_day=8,
                  payment_day=(start + timedelta(days=days)).date(), transcript=HISTORY_MARK, rule_verified=False)
        db.add(job)
        db.flush()
        terms = ag.build_terms(job, rate)
        a = Agreement(job_id=job.id, worker_id=worker.id, hirer_id=job.hirer_id, terms=terms, terms_hash=ag.terms_hash(terms))
        db.add(a)
        db.flush()
        db.add(Assignment(job_id=job.id, worker_id=worker.id, agreement_id=a.id, status="completed", rating=stars,
                          payment_report="paid", payment_reported_at=start + timedelta(days=days), hirer_payment_claim="paid"))


def accounts(db: Session) -> list[dict]:
    users = ensure(db)
    return [{"role": r, "name": u.name, "phone": u.phone} for r, u in (("hirer", users["hirer"]), ("worker", users["worker"]))]
