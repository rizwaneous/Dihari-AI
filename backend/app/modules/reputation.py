"""Reputation + worker tiers ("Dihari Score"). All inputs are records the app already keeps; rules live in
config/tiers.json so they can be tuned without code changes."""
import json
import math
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import Agreement, Assignment, Job, User
from ..settings import get_settings


def first_name(user: User | None) -> str:
    return (user.name or "").split(" ")[0] if user and user.name else "—"


def hirer_reputation(db: Session, hirer_id: str) -> dict:
    rows = db.execute(select(Assignment.payment_report, func.count()).join(Job, Job.id == Assignment.job_id)
                      .where(Job.hirer_id == hirer_id, Assignment.payment_report.is_not(None))
                      .group_by(Assignment.payment_report)).all()
    c = {k: n for k, n in rows}
    paid, unpaid = c.get("paid", 0), c.get("unpaid", 0)
    jobs_posted = db.scalar(select(func.count()).select_from(Job).where(Job.hirer_id == hirer_id))
    rate = paid / (paid + unpaid) if paid + unpaid else None
    return {"on_time_payment_rate": rate, "reports": paid + unpaid, "jobs_posted": jobs_posted, "self_reported": True,
            "pays_on_time_badge": bool(rate is not None and paid + unpaid >= 3 and rate >= 0.9)}


@lru_cache
def _tier_rules(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def tier_rules() -> dict:
    return _tier_rules(str(Path(get_settings().config_dir) / "tiers.json"))


def smoothed_rating(total_stars: float, n: int, rules: dict | None = None) -> float | None:
    """Bayesian average so one bad (or one great) rating cannot swing a new worker's score."""
    if not n:
        return None
    p = (rules or tier_rules())["rating_prior"]
    return (total_stars + p["weight"] * p["mean"]) / (n + p["weight"])


def _qualifies(t: dict, jobs: int, show_up: float | None, rating: float | None, hirers: int) -> bool:
    return (jobs >= t["min_jobs"] and (t["min_show_up"] == 0 or (show_up or 0) >= t["min_show_up"])
            and (t["min_rating"] == 0 or (rating or 0) >= t["min_rating"]) and hirers >= t["min_hirers"])


def worker_tier(db: Session, worker_id: str) -> dict:
    rules = tier_rules()
    since = utcnow() - timedelta(days=rules["window_days"])
    rows = db.execute(select(Assignment.status, Assignment.rating, Job.hirer_id).join(Job, Job.id == Assignment.job_id)
                      .where(Assignment.worker_id == worker_id, Job.start_at >= since)).all()
    done = [r for r in rows if r.status == "completed"]
    bad = sum(1 for r in rows if r.status in ("no_show", "cancelled"))
    jobs = len(done)
    show_up = jobs / (jobs + bad) if jobs + bad else None
    ratings = [r.rating for r in done if r.rating]
    # at most 2 ratings per hirer count, so one friendly hirer cannot inflate a score
    per_hirer: dict[str, list[int]] = {}
    for r in done:
        if r.rating:
            per_hirer.setdefault(r.hirer_id, []).append(r.rating)
    counted = [x for v in per_hirer.values() for x in v[:2]]
    rating = smoothed_rating(sum(counted), len(counted), rules)
    hirers = len({r.hirer_id for r in done})
    tiers = rules["tiers"]
    level = max(i for i, t in enumerate(tiers) if _qualifies(t, jobs, show_up, rating, hirers))
    cur = tiers[level]
    out = {"code": cur["code"], "level": level, "icon": cur["icon"], "color": cur["color"], "boost": cur["boost"],
           "stats": {"jobs": jobs, "show_up": show_up, "rating": math.floor(rating * 10) / 10 if rating else None,
                     "raw_ratings": len(ratings), "hirers": hirers, "window_days": rules["window_days"]},
           "next": None, "progress": 1.0}
    if level + 1 < len(tiers):
        nxt = tiers[level + 1]
        needs = {}
        if jobs < nxt["min_jobs"]:
            needs["jobs"] = nxt["min_jobs"] - jobs
        if nxt["min_show_up"] and (show_up or 0) < nxt["min_show_up"]:
            needs["show_up"] = nxt["min_show_up"]
        if nxt["min_rating"] and (rating or 0) < nxt["min_rating"]:
            needs["rating"] = nxt["min_rating"]
        if hirers < nxt["min_hirers"]:
            needs["hirers"] = nxt["min_hirers"] - hirers
        parts = [min(1, jobs / nxt["min_jobs"]) if nxt["min_jobs"] else 1,
                 min(1, hirers / nxt["min_hirers"]) if nxt["min_hirers"] else 1]
        out["next"] = {"code": nxt["code"], "icon": nxt["icon"], "needs": needs}
        out["progress"] = round(sum(parts) / len(parts), 2)
    return out


def worker_reputation(db: Session, worker_id: str) -> dict:
    rows = db.execute(select(Assignment.status, func.count()).where(Assignment.worker_id == worker_id)
                      .group_by(Assignment.status)).all()
    c = {k: n for k, n in rows}
    done, bad = c.get("completed", 0), c.get("no_show", 0) + c.get("cancelled", 0)
    avg, n = db.execute(select(func.avg(Assignment.rating), func.count(Assignment.rating))
                        .where(Assignment.worker_id == worker_id, Assignment.rating.is_not(None))).one()
    return {"completion_rate": done / (done + bad) if done + bad else None, "jobs_completed": done,
            "avg_rating": float(avg) if avg is not None else None, "ratings": n, "tier": worker_tier(db, worker_id)}


def worker_stats(db: Session, worker_id: str) -> dict:
    """Earnings + the "Kaam Card": a work history built only from agreements both sides saw."""
    rows = db.execute(select(Assignment, Agreement, Job).join(Agreement, Agreement.id == Assignment.agreement_id)
                      .join(Job, Job.id == Assignment.job_id)
                      .where(Assignment.worker_id == worker_id, Assignment.status == "completed")
                      .order_by(Job.start_at.desc())).all()
    now = utcnow()
    week, month, total, owed = 0, 0, 0, 0
    trades: dict[str, int] = {}
    history = []
    for asg, agr, job in rows:
        amount = int(agr.terms["daily_rate"]) * int(agr.terms.get("days") or 1)
        if asg.payment_report == "unpaid":
            owed += amount
        else:
            total += amount
            if job.start_at >= now - timedelta(days=7):
                week += amount
            if job.start_at >= now - timedelta(days=30):
                month += amount
        trades[job.task] = trades.get(job.task, 0) + int(agr.terms.get("days") or 1)
        history.append({"job_id": job.id, "task": job.task, "location_text": job.location_text, "start_at": job.start_at.isoformat(),
                        "days": agr.terms.get("days"), "daily_rate": agr.terms["daily_rate"], "rating": asg.rating,
                        "paid": asg.payment_report, "proof": agr.terms_hash[:10]})
    return {"earned_week": week, "earned_month": month, "earned_total": total, "owed": owed, "days_by_trade": trades,
            "history": history[:20], "tier": worker_tier(db, worker_id)}
