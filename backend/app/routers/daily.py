"""Round 2 endpoints: free today, invites, attendance, hisaab, teams, safety, skills, shareable Kaam Card."""
import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, need_role
from ..models import Assignment, Job, LedgerEntry, Team, User
from ..modules import daily, reputation
from ..views import job_view

router = APIRouter(tags=["daily"])


def _e(e: daily.DailyError):
    status = 403 if e.code == "forbidden" else 404 if e.code in ("no_worker",) else 409
    return HTTPException(status, {"code": e.code, "detail": e.detail})


def _asg(db: Session, asg_id: str) -> Assignment:
    a = db.get(Assignment, asg_id)
    if not a:
        raise HTTPException(404)
    return a


# ---------------------------------------------------------------- free today + invites
class AvailIn(BaseModel):
    available: bool
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)


@router.post("/me/available")
def set_available(body: AvailIn, user: User = Depends(need_role("worker")), db: Session = Depends(get_db)):
    return daily.set_available(db, user, body.available, body.lat, body.lon)


@router.get("/workers/available")
def available(lat: float, lon: float, trade: str | None = None, radius_km: float = 15,
              user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    return daily.available_workers(db, user, lat, lon, trade, min(radius_km, 40))


class InviteIn(BaseModel):
    worker_id: str


@router.post("/jobs/{job_id}/invite", status_code=201)
def invite(job_id: str, body: InviteIn, user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404)
    try:
        inv = daily.invite(db, j, user, body.worker_id)
    except daily.DailyError as e:
        raise _e(e)
    return {"id": inv.id, "status": inv.status}


@router.get("/my/invites")
def my_invites(user: User = Depends(need_role("worker")), db: Session = Depends(get_db)):
    return [{"invite_id": i.id, "job": job_view(db, db.get(Job, i.job_id), user)} for i in daily.my_invites(db, user)]


@router.post("/jobs/{job_id}/decline-invite")
def decline(job_id: str, user: User = Depends(need_role("worker")), db: Session = Depends(get_db)):
    daily.mark_invite(db, job_id, user.id, "declined")
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- attendance
class Where(BaseModel):
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)


@router.post("/assignments/{asg_id}/check-in")
def check_in(asg_id: str, body: Where, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        row = daily.check_in(db, _asg(db, asg_id), user, body.lat, body.lon)
    except daily.DailyError as e:
        raise _e(e)
    return {"day": row.day.isoformat(), "distance_m": row.distance_m, "far": bool(row.distance_m and row.distance_m > 500)}


@router.post("/assignments/{asg_id}/check-out")
def check_out(asg_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        row = daily.check_out(db, _asg(db, asg_id), user)
    except daily.DailyError as e:
        raise _e(e)
    return {"day": row.day.isoformat(), "out": row.check_out_at.isoformat()}


def _party(db: Session, asg: Assignment, user: User) -> None:
    if user.id not in (asg.worker_id, db.get(Job, asg.job_id).hirer_id):
        raise HTTPException(404)


@router.get("/assignments/{asg_id}/attendance")
def attendance(asg_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _asg(db, asg_id)
    _party(db, a, user)
    return daily.attendance_view(db, a)


# ---------------------------------------------------------------- hisaab
class EntryIn(BaseModel):
    kind: str = Field(pattern="^(advance|kharchi|payment|deduction)$")
    amount: int = Field(gt=0, le=10_000_000)
    method: str | None = Field(default=None, pattern="^(cash|jazzcash|easypaisa|bank)$")
    reference: str | None = Field(default=None, max_length=40)
    note: str | None = Field(default=None, max_length=120)


@router.get("/assignments/{asg_id}/hisaab")
def get_hisaab(asg_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _asg(db, asg_id)
    _party(db, a, user)
    return daily.hisaab(db, a, user.locale)


@router.post("/assignments/{asg_id}/hisaab", status_code=201)
def add_hisaab(asg_id: str, body: EntryIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _asg(db, asg_id)
    try:
        daily.add_entry(db, a, user, body.kind, body.amount, body.method, body.reference, body.note)
    except daily.DailyError as e:
        raise _e(e)
    return daily.hisaab(db, a, user.locale)


@router.post("/hisaab/{entry_id}/confirm")
def confirm(entry_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = db.get(LedgerEntry, entry_id)
    if not e:
        raise HTTPException(404)
    try:
        daily.confirm_entry(db, e, user)
    except daily.DailyError as err:
        raise _e(err)
    return daily.hisaab(db, db.get(Assignment, e.assignment_id), user.locale)


# ---------------------------------------------------------------- teams
class TeamIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class MemberIn(BaseModel):
    phone: str
    name: str | None = Field(default=None, max_length=80)


class BookTeamIn(BaseModel):
    worker_ids: list[str]


def _team(db: Session, team_id: str, user: User) -> Team:
    t = db.get(Team, team_id)
    if not t or t.owner_id != user.id:
        raise HTTPException(404)
    return t


@router.get("/teams")
def teams(user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    from sqlalchemy import select
    return [daily.team_view(db, t, user.locale) for t in db.scalars(select(Team).where(Team.owner_id == user.id))]


@router.post("/teams", status_code=201)
def new_team(body: TeamIn, user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    return daily.team_view(db, daily.create_team(db, user, body.name), user.locale)


@router.post("/teams/{team_id}/members", status_code=201)
def add_member(team_id: str, body: MemberIn, user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    t = _team(db, team_id, user)
    try:
        daily.add_member(db, t, user, body.phone, body.name)
    except daily.DailyError as e:
        raise _e(e)
    return daily.team_view(db, t, user.locale)


@router.delete("/teams/{team_id}/members/{worker_id}")
def remove_member(team_id: str, worker_id: str, user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    t = _team(db, team_id, user)
    daily.remove_member(db, t, user, worker_id)
    return daily.team_view(db, t, user.locale)


@router.post("/jobs/{job_id}/book-team")
def book_team(job_id: str, body: BookTeamIn, user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404)
    try:
        asgs = daily.book_team(db, j, user, body.worker_ids)
    except daily.DailyError as e:
        raise _e(e)
    return [{"assignment_id": a.id, "worker_id": a.worker_id} for a in asgs]


@router.get("/teams/{team_id}/payroll")
def payroll(team_id: str, days: int = 7, format: str = "json", user: User = Depends(need_role("hirer")),
            db: Session = Depends(get_db)):
    p = daily.payroll(db, _team(db, team_id, user), user, max(1, min(days, 90)))
    if format != "csv":
        return p
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["name", "phone", "days", "earned", "received", "balance", "currency"])
    for r in p["rows"]:
        w.writerow([r["name"], r["phone"], r["days"], r["earned"], r["received"], r["balance"], p["currency"]])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="payroll-{days}d.csv"'})


# ---------------------------------------------------------------- safety
class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    phone: str


@router.put("/me/safety-contact")
def safety_contact(body: ContactIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        c = daily.set_safety_contact(db, user, body.name, body.phone)
    except daily.DailyError as e:
        raise HTTPException(400, {"code": e.code})
    return {"name": c.name, "phone": c.phone}


@router.post("/safety/sos")
def sos(body: Where, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return daily.sos(db, user, body.lat, body.lon)


# ---------------------------------------------------------------- skills
class EndorseIn(BaseModel):
    trade: str
    years: int | None = Field(default=None, ge=0, le=60)


@router.post("/workers/{worker_id}/endorse", status_code=201)
def endorse(worker_id: str, body: EndorseIn, user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    try:
        daily.endorse(db, user, worker_id, body.trade, body.years)
    except daily.DailyError as e:
        raise _e(e)
    return {"skills": daily.skills_of(db, worker_id)}


# ---------------------------------------------------------------- shareable Kaam Card
@router.get("/my/card-link")
def card_link(user: User = Depends(need_role("worker"))):
    return {"token": daily.card_token(user.id), "path": f"/card/{daily.card_token(user.id)}"}


@router.get("/public/card/{token}")
def public_card(token: str, db: Session = Depends(get_db)):
    """What anyone with the link may see: first name, level, counts, skills and job history without addresses."""
    u = daily.card_user(db, token)
    if not u or u.role != "worker":
        raise HTTPException(404)
    s = reputation.worker_stats(db, u.id)
    return {"first_name": reputation.first_name(u), "tier": s["tier"], "skills": s["skills"],
            "days_by_trade": s["days_by_trade"], "verified_phone": u.phone_verified,
            "history": [{k: h[k] for k in ("task", "start_at", "days", "rating", "proof")} for h in s["history"]]}
