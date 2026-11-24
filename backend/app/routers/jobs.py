from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..country_config import get_country
from ..db import get_db, utcnow
from ..deps import current_user, need_role
from ..models import Assignment, Job, JobStatus as S, Offer, User, WorkerProfile
from ..modules import agreements, geo, jobs, offers, payments, wage_floor
from ..views import job_view, rank_offers

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobIn(BaseModel):
    task: str
    headcount: int = Field(ge=1, le=200)
    location_text: str
    address_detail: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    start_at: datetime
    days: int = Field(default=1, ge=1, le=60)
    daily_rate: int = Field(gt=0)
    hours_per_day: float = Field(gt=0, le=24)
    payment_day: date | None = None
    advance: int = Field(default=0, ge=0)
    deductions: list[dict] = []
    transport_mode: str = "none"
    transport_amount: int | None = None
    transcript: str | None = None
    readback_verified: bool = False


class WageCheckIn(BaseModel):
    country: str | None = None
    region: str | None = None
    location_text: str | None = None
    daily_rate: int | None = None
    hours_per_day: float | None = None
    payment_day: date | None = None
    start_date: date | None = None
    days: int = 1
    deductions: list[dict] = []
    lang: str = "ur"


class OfferIn(BaseModel):
    rate: int | None = None


class AssignIn(BaseModel):
    offer_ids: list[str]


class CompleteIn(BaseModel):
    absent_assignment_ids: list[str] = []


def _http(e: Exception, status=400):
    return HTTPException(status, {"code": getattr(e, "code", str(e)), "detail": getattr(e, "detail", None)})


@router.post("", status_code=201)
def create(body: JobIn, user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    try:
        j = jobs.create_job(db, user, body.model_dump(exclude={"transcript", "readback_verified"}),
                            transcript=body.transcript, readback_verified=body.readback_verified)
    except jobs.JobRejected as e:
        raise _http(e, 422 if e.code in ("wage_floor", "missing_fields", "location_unresolved") else 429 if e.code in ("rate_limited", "daily_limit", "too_many_open") else 409 if e.code == "duplicate" else 403)
    return job_view(db, j, user)


@router.post("/check-wage")
def check_wage(body: WageCheckIn, db: Session = Depends(get_db)):
    cfg = get_country(body.country)
    region = body.region or cfg.resolve_region(body.location_text)
    r = wage_floor.check(country=cfg.code, region=region, daily_rate=body.daily_rate, hours_per_day=body.hours_per_day,
                         payment_day=body.payment_day, start_date=body.start_date, days=body.days,
                         deductions=body.deductions, on=date.today())
    return r.to_dict(body.lang)


@router.get("/mine")
def mine(user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    js = db.scalars(select(Job).where(Job.hirer_id == user.id).order_by(Job.created_at.desc())).all()
    out = []
    for j in js:
        v = job_view(db, j, user)
        v["offer_count"] = len(db.scalars(select(Offer).where(Offer.job_id == j.id, Offer.status.in_(["pending", "selected"]))).all())
        out.append(v)
    return out


@router.get("/nearby")
def nearby(lat: float | None = None, lon: float | None = None, radius_km: float | None = None, all_trades: bool = False,
           user: User = Depends(need_role("worker")), db: Session = Depends(get_db)):
    wp = db.get(WorkerProfile, user.id)
    cfg = get_country(user.country_code)
    lat = lat if lat is not None else (wp.lat if wp else None)
    lon = lon if lon is not None else (wp.lon if wp else None)
    if lat is None or lon is None:
        raise HTTPException(400, {"code": "no_location"})
    radius = min(radius_km or (wp.radius_km if wp else cfg.default_radius_km), cfg.max_radius_km)
    res = geo.nearby_jobs(db, lat, lon, radius, trades=(wp.trades if wp and wp.trades and not all_trades else None), country=user.country_code)
    return [job_view(db, j, user, from_lat=lat, from_lon=lon) for j, _ in res]


@router.get("/{job_id}")
def get_job(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j or j.country_code != user.country_code:
        raise HTTPException(404)
    return job_view(db, j, user)


@router.get("/{job_id}/assignments")
def list_assignments(job_id: str, user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    from ..modules import reputation
    j = db.get(Job, job_id)
    if not j or j.hirer_id != user.id:
        raise HTTPException(404)
    out = []
    for a in db.scalars(select(Assignment).where(Assignment.job_id == job_id)):
        w = db.get(User, a.worker_id)
        out.append({"assignment_id": a.id, "agreement_id": a.agreement_id, "status": a.status, "first_name": reputation.first_name(w),
                    "phone": w.phone, "my_payment_claim": a.hirer_payment_claim, "rating": a.rating})
    return out


@router.get("/{job_id}/offers")
def list_offers(job_id: str, sort: str = "best", user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j or j.hirer_id != user.id:
        raise HTTPException(404)
    if sort not in ("best", "distance", "price", "rating", "reliability"):
        raise HTTPException(400, "bad sort")
    return rank_offers(db, j, sort)


@router.post("/{job_id}/offers", status_code=201)
def post_offer(job_id: str, body: OfferIn, user: User = Depends(need_role("worker")), db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j or j.country_code != user.country_code:
        raise HTTPException(404)
    try:
        o = offers.make_offer(db, j, user, body.rate)
    except offers.OfferError as e:
        raise _http(e, 422 if e.code.startswith("counter") else 409)
    return {"id": o.id, "rate": o.rate, "kind": o.kind, "status": o.status}


@router.post("/{job_id}/book")
def book(job_id: str, worker: User = Depends(need_role("worker")), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job or job.country_code != worker.country_code:
        raise HTTPException(404)
    jobs.lock_for_booking(db, job)
    existing = db.scalar(select(Assignment).where(Assignment.job_id == job.id,
                                                  Assignment.worker_id == worker.id))
    if existing and existing.status in ("assigned", "confirmed"):
        return {"assignment_id": existing.id, "status": existing.status, "agreement_id": existing.agreement_id}
    if job.start_at < utcnow():
        raise HTTPException(409, "job_expired")
    try:
        offer = offers.make_offer(db, job, worker, commit=False)
        owner = db.get(User, job.hirer_id)
        assignment, = agreements.select_workers(db, job, owner, [offer.id], direct=True)
    except (offers.OfferError, agreements.AgreementError) as e:
        db.rollback()
        raise _http(e, 409)
    return {"assignment_id": assignment.id, "status": assignment.status, "agreement_id": assignment.agreement_id}


@router.delete("/offers/{offer_id}")
def withdraw(offer_id: str, user: User = Depends(need_role("worker")), db: Session = Depends(get_db)):
    o = db.get(Offer, offer_id)
    if not o:
        raise HTTPException(404)
    try:
        offers.withdraw(db, o, user)
    except offers.OfferError as e:
        raise _http(e, 409)
    return {"ok": True}


@router.post("/{job_id}/assign")
def assign(job_id: str, body: AssignIn, user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404)
    try:
        asgs = agreements.select_workers(db, j, user, body.offer_ids)
    except agreements.AgreementError as e:
        raise _http(e, 403 if e.code == "forbidden" else 409)
    return [{"assignment_id": a.id, "agreement_id": a.agreement_id, "worker_id": a.worker_id} for a in asgs]


@router.post("/{job_id}/start")
def start(job_id: str, user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    j = db.get(Job, job_id) or (_ for _ in ()).throw(HTTPException(404))
    try:
        payments.start_job(db, j, user)
    except (payments.PaymentError, jobs.IllegalTransition) as e:
        raise _http(e, 409)
    return {"status": j.status}


@router.post("/{job_id}/complete")
def complete(job_id: str, body: CompleteIn, user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    j = db.get(Job, job_id) or (_ for _ in ()).throw(HTTPException(404))
    try:
        payments.complete_job(db, j, user, body.absent_assignment_ids)
    except (payments.PaymentError, jobs.IllegalTransition) as e:
        raise _http(e, 409)
    return {"status": j.status}


@router.post("/{job_id}/cancel")
def cancel(job_id: str, user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j or j.hirer_id != user.id:
        raise HTTPException(404)
    jobs.lock_for_booking(db, j)
    try:
        jobs.transition(db, j, S.cancelled, user.id)
    except jobs.IllegalTransition as e:
        raise _http(e, 409)
    from ..modules.notifications import notify
    for assignment in db.scalars(select(Assignment).where(Assignment.job_id == j.id,
                                                           Assignment.status.in_(["assigned", "confirmed"]))):
        assignment.status = "cancelled"
        notify(db, assignment.worker_id, "job_cancelled", j.id)
    db.commit()
    return {"status": j.status}
