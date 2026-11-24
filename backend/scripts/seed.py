"""Demo data: realistic Islamabad/Rawalpindi workers, hirers and jobs. Idempotent, deterministic.
Usage: python scripts/seed.py [--country PK]   (reads DATABASE_URL)"""
import argparse
import hashlib
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select  # noqa: E402

from app.country_config import get_country  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import HirerProfile, Reviewer, User, WorkerProfile  # noqa: E402
from app.modules import jobs, offers  # noqa: E402

FIRST = ["Ali", "Bilal", "Imran", "Kamran", "Shahid", "Rashid", "Waseem", "Irfan", "Zubair", "Tariq", "Naveed", "Asif",
         "Farooq", "Javed", "Sajid", "Nadeem", "Mansoor", "Yasir", "Saeed", "Adnan", "Rizwan", "Khalid", "Amjad", "Haroon"]
LAST = ["Khan", "Ahmed", "Hussain", "Shah", "Malik", "Butt", "Raza", "Iqbal", "Abbasi", "Awan"]
HIRERS = [("Kamran Contractor", "contractor"), ("Sana Malik", "household"), ("Tariq Builders", "business"),
          ("Rubina Bibi", "household"), ("Zahid Constructions", "contractor"), ("Nadia Ahmed", "household")]
# trade -> typical daily rates (all >= the placeholder floor; the floor module is the authority)
RATES = {"tile": (1400, 1900), "mason": (1500, 2200), "paint": (1200, 1700), "plumber": (1400, 2000),
         "electrician": (1400, 2000), "labour": (1000, 1300), "carpenter": (1500, 2100), "shifting": (1000, 1400)}


def phone(cfg, n: int) -> str:
    return cfg.normalize_phone(f"03{n:09d}"[:11]) or ""


def seed(db, country: str = None, n_workers: int = 30, rng_seed: int = 7) -> dict:
    cfg = get_country(country)
    rng = random.Random(rng_seed)
    if db.scalars(select(User)).first():
        from app.modules import demo
        demo.ensure(db)   # older demo databases also get the demo history
        return {"skipped": True}
    tz = ZoneInfo(cfg.timezone)
    places = cfg.places
    workers, hirers = [], []
    for i in range(n_workers):
        u = User(phone=phone(cfg, 2_000_000 + i), country_code=cfg.code, role="worker", locale=cfg.default_language,
                 name=f"{rng.choice(FIRST)} {rng.choice(LAST)}", phone_verified=True)
        db.add(u); db.flush()
        pl = rng.choice(places)
        trades = rng.sample([t.code for t in cfg.trades if not t.generic], k=rng.choice([1, 1, 2])) + (["labour"] if rng.random() < .35 else [])
        db.add(WorkerProfile(user_id=u.id, trades=trades, area_name=pl.name, lat=pl.lat + rng.uniform(-.01, .01),
                             lon=pl.lon + rng.uniform(-.01, .01), radius_km=rng.choice([5, 8, 10, 15])))
        workers.append(u)
    for i, (name, typ) in enumerate(HIRERS):
        u = User(phone=phone(cfg, 1_000_000 + i), country_code=cfg.code, role="hirer", locale=cfg.default_language, name=name, phone_verified=True)
        db.add(u); db.flush(); db.add(HirerProfile(user_id=u.id, hirer_type=typ)); hirers.append(u)
    db.commit()
    made = []
    for k in range(18):
        h = hirers[k % len(hirers)]
        trade = rng.choice([t.code for t in cfg.trades])
        lo, hi = RATES.get(trade, (1000, 1500))
        start = (datetime.now(tz) + timedelta(days=rng.choice([1, 1, 2, 3]))).replace(hour=rng.choice([7, 8, 9]), minute=0, second=0, microsecond=0)
        days = rng.choice([1, 1, 2, 3])
        pl = rng.choice(places)
        try:
            j = jobs.create_job(db, h, dict(task=trade, headcount=rng.choice([1, 2, 3, 4, 6]), location_text=pl.name,
                address_detail=f"House {rng.randint(1, 120)}, Street {rng.randint(1, 30)}", start_at=start.astimezone(timezone.utc),
                days=days, daily_rate=rng.randrange(lo, hi + 1, 50), hours_per_day=rng.choice([8, 8, 8, 7]),
                payment_day=(start + timedelta(days=days + rng.choice([0, 1, 2]))).date(), advance=rng.choice([0, 0, 500]),
                deductions=[], transport_mode=rng.choice(["none", "provided", "none"])))
            made.append(j)
        except jobs.JobRejected:
            continue
    for j in made[:8]:  # some already have offers
        near = [w for w in workers if rng.random() < .25]
        for w in near[:3]:
            try:
                offers.make_offer(db, j, w, None if rng.random() < .6 else j.daily_rate + rng.choice([100, 200, 300]))
            except offers.OfferError:
                pass
    token = os.environ.get("DEMO_REVIEWER_TOKEN", "demo-reviewer-token")
    db.add(Reviewer(name="Demo Reviewer", token_hash=hashlib.sha256(token.encode()).hexdigest()))
    db.commit()
    from app.modules import demo
    demo.ensure(db)   # demo labourer gets a work history so the tier + Kaam Card have something to show
    return {"workers": len(workers), "hirers": len(hirers), "jobs": len(made), "demo_hirer_phone": "03" + f"{1_000_000:09d}",
            "demo_worker_phone": "03" + f"{2_000_000:09d}", "reviewer_token": token}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--country", default=None); a = ap.parse_args()
    init_db()
    with SessionLocal() as db:
        print(seed(db, a.country))
