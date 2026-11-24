"""Geo matching. PostGIS ST_DWithin on Postgres; haversine on other dialects (tests)."""
import hashlib
import hmac
import math

from sqlalchemy import and_, select, text
from sqlalchemy.orm import Session

from ..models import Job, JobStatus as S
from ..settings import get_settings
from ..db import utcnow
from .jobs import booked_count

EARTH_M = 6371008.8


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_M * math.asin(math.sqrt(a))


def ensure_postgis(engine) -> None:
    with engine.begin() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        c.execute(text("CREATE INDEX IF NOT EXISTS jobs_geo_gist ON jobs USING GIST "
                       "((ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography))"))


POSTGIS_DWITHIN_SQL = ("ST_DWithin(ST_SetSRID(ST_MakePoint(jobs.lon, jobs.lat), 4326)::geography, "
                       "ST_SetSRID(ST_MakePoint(:qlon, :qlat), 4326)::geography, :qr)")


def dwithin_clause(lat: float, lon: float, radius_m: float):
    return text(POSTGIS_DWITHIN_SQL).bindparams(qlat=lat, qlon=lon, qr=radius_m)


def _bbox(lat, lon, radius_m):
    dlat = math.degrees(radius_m / EARTH_M)
    dlon = math.degrees(radius_m / (EARTH_M * max(math.cos(math.radians(lat)), 0.01)))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


def nearby_jobs(db: Session, lat: float, lon: float, radius_km: float, *, trades: list[str] | None = None,
                country: str | None = None, limit: int = 50) -> list[tuple[Job, float]]:
    """Open jobs within radius, nearest first. Excludes flagged jobs."""
    r = radius_km * 1000
    q = select(Job).where(Job.status.in_([S.open.value, S.offers.value, S.assigned.value]),
                          booked_count() < Job.headcount, Job.start_at >= utcnow(), Job.flagged == False)  # noqa: E712
    if country:
        q = q.where(Job.country_code == country)
    if trades:
        q = q.where(Job.task.in_(trades))
    if db.get_bind().dialect.name == "postgresql":
        q = q.where(dwithin_clause(lat, lon, r))
    else:
        a, b, c, d = _bbox(lat, lon, r)
        q = q.where(and_(Job.lat.between(a, b), Job.lon.between(c, d)))
    out = []
    for j in db.scalars(q):
        dist = haversine_m(lat, lon, j.lat, j.lon)
        if dist <= r:
            out.append((j, dist))
    out.sort(key=lambda x: x[1])
    return out[:limit]


def fuzz_location(job_id: str, lat: float, lon: float) -> tuple[float, float]:
    """Deterministic per-job offset 150..500 m so repeated requests cannot be averaged out."""
    s = get_settings()
    h = hmac.new(s.secret_key.encode(), f"fuzz:{job_id}".encode(), hashlib.sha256).digest()
    ang = int.from_bytes(h[:4], "big") / 2**32 * 2 * math.pi
    dist = s.geo_fuzz_min_m + int.from_bytes(h[4:8], "big") / 2**32 * (s.geo_fuzz_max_m - s.geo_fuzz_min_m)
    dlat = math.degrees(dist * math.cos(ang) / EARTH_M)
    dlon = math.degrees(dist * math.sin(ang) / (EARTH_M * math.cos(math.radians(lat))))
    return round(lat + dlat, 5), round(lon + dlon, 5)


def nearby_workers(db: Session, lat: float, lon: float, radius_km: float, *, trade: str | None = None,
                   country: str | None = None, limit: int | None = 50):
    """Workers whose profile point is within radius. Returns [(User, WorkerProfile, dist_m)] nearest first."""
    from ..models import User, WorkerProfile
    r = radius_km * 1000
    q = select(User, WorkerProfile).join(WorkerProfile, WorkerProfile.user_id == User.id).where(
        WorkerProfile.lat.is_not(None), User.suspended == False)  # noqa: E712
    if country:
        q = q.where(User.country_code == country)
    if db.get_bind().dialect.name == "postgresql":
        q = q.where(text("ST_DWithin(ST_SetSRID(ST_MakePoint(worker_profiles.lon, worker_profiles.lat), 4326)::geography, "
                         "ST_SetSRID(ST_MakePoint(:wlon, :wlat), 4326)::geography, :wr)").bindparams(wlat=lat, wlon=lon, wr=r))
    else:
        a, b, c, d = _bbox(lat, lon, r)
        q = q.where(WorkerProfile.lat.between(a, b), WorkerProfile.lon.between(c, d))
    out = []
    for u, wp in db.execute(q):
        if trade and trade not in (wp.trades or []):
            continue
        dist = haversine_m(lat, lon, wp.lat, wp.lon)
        if dist <= r:
            out.append((u, wp, dist))
    out.sort(key=lambda x: x[2])
    return out[:limit]
