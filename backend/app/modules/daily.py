"""Round 2 practical features, kept in plain code (no AI decides money or attendance):

* availability   "Aaj farigh hoon" (free today) + hirer sees free workers nearby and invites one directly
* attendance     site check-in / check-out with distance from the job site
* hisaab         running account per assignment: earned, advances, kharchi, payments (with proof), deductions
* late cancel    a hirer cancelling close to the start owes each booked worker a small fee (country config)
* teams          a thekedar's crew: roster, book the whole team, today's attendance, payroll
* safety         emergency contact + SOS
* skills         hirers who completed a job with a worker can vouch for a skill
"""
import hashlib
import hmac
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import i18n
from ..country_config import get_country
from ..db import utcnow
from ..models import (Agreement, Assignment, Attendance, Availability, Endorsement, Incident, Invite, Job,
                      JobStatus as S, LedgerEntry, SafetyContact, Team, TeamMember, User, WorkerProfile)
from ..settings import get_settings
from . import audit, geo, reputation
from .notifications import get_sms, notify


class DailyError(Exception):
    def __init__(self, code: str, detail=None):
        super().__init__(code)
        self.code, self.detail = code, detail


def _tz(user_or_job) -> ZoneInfo:
    return ZoneInfo(get_country(user_or_job.country_code).timezone)


def local_today(obj, now: datetime | None = None) -> date:
    return (now or utcnow()).astimezone(_tz(obj)).date()


def _money(n: int, cfg, lang: str) -> str:
    cur = i18n.t(f"currency.{cfg.currency.code}", lang) if i18n.get_raw(f"currency.{cfg.currency.code}", lang) else cfg.currency.code
    return f"{n:,} {cur}"


# ------------------------------------------------------------------ availability + invites
def set_available(db: Session, worker: User, available: bool, lat: float | None = None, lon: float | None = None) -> dict:
    row = db.get(Availability, worker.id)
    if not available:
        if row:
            db.delete(row)
        audit.log(db, worker.id, "availability", worker.id, "off")
        db.commit()
        return {"available": False, "until": None}
    tz = _tz(worker)
    end = datetime.combine(local_today(worker) + timedelta(days=1), time(0), tz)   # end of the local day
    wp = db.get(WorkerProfile, worker.id)
    lat = lat if lat is not None else (wp.lat if wp else None)
    lon = lon if lon is not None else (wp.lon if wp else None)
    row = row or Availability(user_id=worker.id)
    row.until, row.lat, row.lon = end, lat, lon
    db.add(row)
    audit.log(db, worker.id, "availability", worker.id, "on")
    db.commit()
    return {"available": True, "until": end.isoformat()}


def is_available(db: Session, worker_id: str) -> bool:
    row = db.get(Availability, worker_id)
    return bool(row and row.until > utcnow())


def available_workers(db: Session, hirer: User, lat: float, lon: float, trade: str | None = None,
                      radius_km: float = 15, limit: int = 40) -> list[dict]:
    cfg = get_country(hirer.country_code)
    now = utcnow()
    rows = db.execute(select(User, Availability, WorkerProfile).join(Availability, Availability.user_id == User.id)
                      .join(WorkerProfile, WorkerProfile.user_id == User.id, isouter=True)
                      .where(Availability.until > now, User.suspended == False, User.country_code == cfg.code)).all()  # noqa: E712
    out = []
    for u, av, wp in rows:
        plat, plon = (av.lat, av.lon) if av.lat is not None else ((wp.lat, wp.lon) if wp else (None, None))
        if plat is None or u.id == hirer.id:
            continue
        if trade and wp and wp.trades and trade not in wp.trades:
            continue
        d = geo.haversine_m(lat, lon, plat, plon)
        if d > radius_km * 1000:
            continue
        out.append({"worker_id": u.id, "first_name": reputation.first_name(u), "trades": (wp.trades if wp else []),
                    "distance_km": round(d / 500) * 0.5, "tier": reputation.worker_tier(db, u.id),
                    "skills": skills_of(db, u.id)})
    out.sort(key=lambda w: (-w["tier"]["level"], w["distance_km"]))
    return out[:limit]


def invite(db: Session, job: Job, hirer: User, worker_id: str) -> Invite:
    if job.hirer_id != hirer.id:
        raise DailyError("forbidden")
    if job.status not in (S.open.value, S.offers.value, S.assigned.value) or job.start_at < utcnow():
        raise DailyError("job_closed")
    worker = db.get(User, worker_id)
    if not worker or worker.role != "worker":
        raise DailyError("no_worker")
    inv = db.scalar(select(Invite).where(Invite.job_id == job.id, Invite.worker_id == worker_id))
    if inv is None:
        inv = Invite(job_id=job.id, worker_id=worker_id, hirer_id=hirer.id)
        db.add(inv)
        db.flush()
        notify(db, worker_id, "invited", job.id)
        audit.log(db, hirer.id, "invite", inv.id, "sent", data={"job": job.id, "worker": worker_id})
    db.commit()
    return inv


def my_invites(db: Session, worker: User) -> list[Invite]:
    return list(db.scalars(select(Invite).join(Job, Job.id == Invite.job_id).where(
        Invite.worker_id == worker.id, Invite.status == "pending", Job.start_at >= utcnow(),
        Job.status.in_([S.open.value, S.offers.value, S.assigned.value])).order_by(Invite.created_at.desc())))


def mark_invite(db: Session, job_id: str, worker_id: str, status: str) -> None:
    inv = db.scalar(select(Invite).where(Invite.job_id == job_id, Invite.worker_id == worker_id))
    if inv and inv.status == "pending":
        inv.status = status
        if status == "declined":
            notify(db, inv.hirer_id, "invite_declined", job_id)


def notify_urgent(db: Session, job: Job) -> int:
    """'Abhi chahiye': ping every worker who said they are free today within the country's urgent radius."""
    cfg = get_country(job.country_code)
    n = 0
    for w in available_workers(db, db.get(User, job.hirer_id), job.lat, job.lon, None, cfg.urgent_radius_km, 200):
        notify(db, w["worker_id"], "urgent_job", job.id)
        n += 1
    return n


# ------------------------------------------------------------------ attendance
def _site_distance(job: Job, lat: float | None, lon: float | None) -> int | None:
    return None if lat is None or lon is None else int(geo.haversine_m(lat, lon, job.lat, job.lon))


def check_in(db: Session, asg: Assignment, actor: User, lat: float | None = None, lon: float | None = None,
             now: datetime | None = None) -> Attendance:
    job = db.get(Job, asg.job_id)
    by_hirer = actor.id == job.hirer_id
    if actor.id != asg.worker_id and not by_hirer:
        raise DailyError("forbidden")
    if asg.status != "confirmed" or job.status not in (S.assigned.value, S.in_progress.value):
        raise DailyError("not_active")
    now = now or utcnow()
    today = local_today(job, now)
    first = job.start_at.astimezone(_tz(job)).date()
    if not first <= today <= first + timedelta(days=max(job.days, 1) - 1):
        raise DailyError("not_a_work_day", {"first": first.isoformat(), "days": job.days})
    row = db.scalar(select(Attendance).where(Attendance.assignment_id == asg.id, Attendance.day == today))
    if row is None:
        row = Attendance(assignment_id=asg.id, day=today, check_in_at=now, distance_m=_site_distance(job, lat, lon),
                         marked_by="hirer" if by_hirer else "worker")
        db.add(row)
        audit.log(db, actor.id, "attendance", asg.id, "check_in", data={"day": today.isoformat(), "distance_m": row.distance_m})
        notify(db, job.hirer_id if not by_hirer else asg.worker_id, "checked_in", job.id)
    db.commit()
    return row


def check_out(db: Session, asg: Assignment, actor: User, now: datetime | None = None) -> Attendance:
    job = db.get(Job, asg.job_id)
    if actor.id not in (asg.worker_id, job.hirer_id):
        raise DailyError("forbidden")
    now = now or utcnow()
    row = db.scalar(select(Attendance).where(Attendance.assignment_id == asg.id, Attendance.day == local_today(job, now)))
    if row is None:
        raise DailyError("not_checked_in")
    if row.check_out_at is None:
        row.check_out_at = now
        audit.log(db, actor.id, "attendance", asg.id, "check_out")
    db.commit()
    return row


def attendance_view(db: Session, asg: Assignment) -> list[dict]:
    rows = db.scalars(select(Attendance).where(Attendance.assignment_id == asg.id).order_by(Attendance.day))
    return [{"day": r.day.isoformat(), "in": r.check_in_at and r.check_in_at.isoformat(),
             "out": r.check_out_at and r.check_out_at.isoformat(), "distance_m": r.distance_m,
             "far": bool(r.distance_m and r.distance_m > 500), "marked_by": r.marked_by} for r in rows]


# ------------------------------------------------------------------ hisaab (running account)
CREDIT_KINDS = {"cancellation_fee"}                         # adds to what the hirer owes
DEBIT_KINDS = {"advance", "kharchi", "payment", "deduction"}  # reduces what is still owed
PROOF_METHODS = {"jazzcash", "easypaisa", "bank"}


def add_entry(db: Session, asg: Assignment, actor: User, kind: str, amount: int, method: str | None = None,
              reference: str | None = None, note: str | None = None) -> LedgerEntry:
    job = db.get(Job, asg.job_id)
    is_worker, is_hirer = actor.id == asg.worker_id, actor.id == job.hirer_id
    if not (is_worker or is_hirer):
        raise DailyError("forbidden")
    if kind not in DEBIT_KINDS or amount <= 0:
        raise DailyError("bad_entry")
    if kind == "deduction" and not is_hirer:
        raise DailyError("forbidden")
    if method and method not in PROOF_METHODS | {"cash"}:
        raise DailyError("bad_method")
    e = LedgerEntry(assignment_id=asg.id, kind=kind, amount=int(amount), method=method, reference=(reference or None),
                    note=note, created_by=actor.id)
    # A worker saying "I received" is the strongest confirmation there is; a hirer's entry waits for the worker.
    if is_worker:
        e.confirmed_at = utcnow()
    db.add(e)
    db.flush()
    audit.log(db, actor.id, "ledger", e.id, f"add_{kind}", data={"assignment": asg.id, "amount": e.amount, "method": method})
    notify(db, job.hirer_id if is_worker else asg.worker_id, "hisaab_entry", job.id)
    db.commit()
    return e


def confirm_entry(db: Session, entry: LedgerEntry, actor: User) -> LedgerEntry:
    asg = db.get(Assignment, entry.assignment_id)
    if actor.id != asg.worker_id or entry.created_by == actor.id:
        raise DailyError("forbidden")
    if entry.confirmed_at is None:
        entry.confirmed_at = utcnow()
        audit.log(db, actor.id, "ledger", entry.id, "confirmed")
    db.commit()
    return entry


def days_worked(db: Session, asg: Assignment, agr: Agreement) -> int:
    n = db.scalar(select(func.count()).select_from(Attendance).where(Attendance.assignment_id == asg.id,
                                                                   Attendance.check_in_at.is_not(None)))
    if n:
        return n
    return int(agr.terms.get("days") or 1) if asg.status == "completed" else 0


def hisaab(db: Session, asg: Assignment, lang: str = "ur") -> dict:
    agr = db.get(Agreement, asg.agreement_id)
    job = db.get(Job, asg.job_id)
    cfg = get_country(job.country_code)
    rate = int(agr.terms["daily_rate"])
    worked = days_worked(db, asg, agr)
    earned = rate * worked
    agreed_ded = sum(int(d.get("amount") or 0) for d in (agr.terms.get("deductions") or [])) if worked else 0
    entries = list(db.scalars(select(LedgerEntry).where(LedgerEntry.assignment_id == asg.id).order_by(LedgerEntry.created_at)))
    tot = {k: 0 for k in DEBIT_KINDS | CREDIT_KINDS}
    pending = 0
    for e in entries:
        if e.confirmed_at is None:
            pending += e.amount
            continue
        tot[e.kind] += e.amount
    received = tot["advance"] + tot["kharchi"] + tot["payment"]
    balance = earned + tot["cancellation_fee"] - agreed_ded - tot["deduction"] - received
    speak = i18n.t("hisaab.speak", lang, earned=_money(earned, cfg, lang), received=_money(received, cfg, lang),
                   balance=_money(max(balance, 0), cfg, lang), days=worked)
    return {"assignment_id": asg.id, "daily_rate": rate, "days_worked": worked, "days_agreed": agr.terms.get("days"),
            "earned": earned, "agreed_deductions": agreed_ded, "received": received, "deductions": tot["deduction"],
            "cancellation_fees": tot["cancellation_fee"], "pending_confirmation": pending, "balance": balance,
            "currency": cfg.currency.code, "speak": speak,
            "entries": [{"id": e.id, "kind": e.kind, "amount": e.amount, "method": e.method, "reference": e.reference,
                         "note": e.note, "by": "worker" if e.created_by == asg.worker_id else "system" if e.created_by == "system" else "hirer",
                         "confirmed": e.confirmed_at is not None,
                         "proof": bool(e.reference and e.method in PROOF_METHODS) or (e.confirmed_at is not None and e.created_by != asg.worker_id and e.kind != "cancellation_fee"),
                         "at": e.created_at.isoformat()} for e in entries]}


# ------------------------------------------------------------------ late cancellation
def charge_late_cancellation(db: Session, job: Job, hirer: User, assignments: list[Assignment]) -> int:
    cfg = get_country(job.country_code)
    if not cfg.late_cancel_fee or not assignments:
        return 0
    if job.start_at - utcnow() > timedelta(hours=cfg.late_cancel_hours):
        return 0
    for a in assignments:
        db.add(LedgerEntry(assignment_id=a.id, kind="cancellation_fee", amount=cfg.late_cancel_fee, created_by="system",
                           confirmed_at=utcnow(), note="late_cancel"))
    audit.log(db, hirer.id, "job", job.id, "late_cancel", data={"workers": len(assignments), "fee": cfg.late_cancel_fee})
    return len(assignments)


def late_cancellations(db: Session, hirer_id: str) -> int:
    return db.scalar(select(func.count(func.distinct(Assignment.job_id))).select_from(LedgerEntry)
                     .join(Assignment, Assignment.id == LedgerEntry.assignment_id).join(Job, Job.id == Assignment.job_id)
                     .where(Job.hirer_id == hirer_id, LedgerEntry.kind == "cancellation_fee")) or 0


# ------------------------------------------------------------------ teams (thekedar)
def create_team(db: Session, owner: User, name: str) -> Team:
    t = Team(owner_id=owner.id, name=name.strip()[:60] or "Team")
    db.add(t)
    db.flush()
    audit.log(db, owner.id, "team", t.id, "created")
    db.commit()
    return t


def add_member(db: Session, team: Team, owner: User, raw_phone: str, name: str | None = None) -> User:
    """Add a worker by phone. Workers without the app are created as unverified accounts the thekedar acts for."""
    if team.owner_id != owner.id:
        raise DailyError("forbidden")
    cfg = get_country(owner.country_code)
    phone = cfg.normalize_phone(raw_phone)
    if not phone:
        raise DailyError("invalid_phone")
    w = db.scalar(select(User).where(User.phone == phone))
    if w is None:
        w = User(phone=phone, country_code=cfg.code, role="worker", locale=owner.locale, name=name, phone_verified=False)
        db.add(w)
        db.flush()
        audit.log(db, owner.id, "user", w.id, "created_by_thekedar")
    elif w.role != "worker":
        raise DailyError("not_worker")
    if name and not w.name:
        w.name = name
    if not db.get(TeamMember, (team.id, w.id)):
        db.add(TeamMember(team_id=team.id, worker_id=w.id))
        audit.log(db, owner.id, "team", team.id, "member_added", data={"worker": w.id})
    db.commit()
    return w


def remove_member(db: Session, team: Team, owner: User, worker_id: str) -> None:
    if team.owner_id != owner.id:
        raise DailyError("forbidden")
    m = db.get(TeamMember, (team.id, worker_id))
    if m:
        db.delete(m)
        audit.log(db, owner.id, "team", team.id, "member_removed", data={"worker": worker_id})
    db.commit()


def team_view(db: Session, team: Team, lang: str = "ur") -> dict:
    members = []
    now = utcnow()
    for m in db.scalars(select(TeamMember).where(TeamMember.team_id == team.id).order_by(TeamMember.added_at)):
        w = db.get(User, m.worker_id)
        wp = db.get(WorkerProfile, w.id)
        today = db.scalar(select(Attendance).join(Assignment, Assignment.id == Attendance.assignment_id)
                          .where(Assignment.worker_id == w.id, Attendance.day == local_today(w, now)))
        members.append({"worker_id": w.id, "name": w.name or w.phone[-4:], "first_name": reputation.first_name(w),
                        "phone": w.phone, "has_app": w.phone_verified, "trades": wp.trades if wp else [],
                        "available": is_available(db, w.id), "checked_in_today": bool(today and today.check_in_at),
                        "tier": reputation.worker_tier(db, w.id)})
    return {"id": team.id, "name": team.name, "members": members}


def book_team(db: Session, job: Job, owner: User, worker_ids: list[str]) -> list[Assignment]:
    """The thekedar books his own crew onto his own job in one step (confirmed directly: he acts for them)."""
    from . import agreements, offers
    if job.hirer_id != owner.id:
        raise DailyError("forbidden")
    member_ids = set(db.scalars(select(TeamMember.worker_id).join(Team, Team.id == TeamMember.team_id)
                                .where(Team.owner_id == owner.id)))
    if not worker_ids or not set(worker_ids) <= member_ids:
        raise DailyError("not_in_team")
    try:
        offer_ids = [offers.make_offer(db, job, db.get(User, w), None, commit=False).id for w in worker_ids]
        return agreements.select_workers(db, job, owner, offer_ids, direct=True)
    except (offers.OfferError, agreements.AgreementError) as e:
        db.rollback()
        raise DailyError(e.code, getattr(e, "detail", None))


def payroll(db: Session, team: Team, owner: User, days: int = 7) -> dict:
    if team.owner_id != owner.id:
        raise DailyError("forbidden")
    since = utcnow() - timedelta(days=days)
    rows = []
    for m in db.scalars(select(TeamMember).where(TeamMember.team_id == team.id)):
        w = db.get(User, m.worker_id)
        tot = {"days": 0, "earned": 0, "received": 0, "balance": 0}
        for asg in db.scalars(select(Assignment).join(Job, Job.id == Assignment.job_id).where(
                Assignment.worker_id == w.id, Job.hirer_id == owner.id, Job.start_at >= since,
                Assignment.status.in_(["confirmed", "completed"]))):
            h = hisaab(db, asg, owner.locale)
            tot["days"] += h["days_worked"]
            tot["earned"] += h["earned"]
            tot["received"] += h["received"]
            tot["balance"] += h["balance"]
        rows.append({"worker_id": w.id, "name": w.name or w.phone, "phone": w.phone, **tot})
    return {"team": team.name, "days": days, "rows": rows,
            "total_balance": sum(r["balance"] for r in rows), "currency": get_country(owner.country_code).currency.code}


# ------------------------------------------------------------------ safety
def set_safety_contact(db: Session, user: User, name: str, raw_phone: str) -> SafetyContact:
    phone = get_country(user.country_code).normalize_phone(raw_phone)
    if not phone:
        raise DailyError("invalid_phone")
    c = db.get(SafetyContact, user.id) or SafetyContact(user_id=user.id)
    c.name, c.phone = name.strip()[:60], phone
    db.add(c)
    db.commit()
    return c


def sos(db: Session, user: User, lat: float | None, lon: float | None) -> dict:
    cfg = get_country(user.country_code)
    notified = []
    where = f" https://maps.google.com/?q={lat},{lon}" if lat is not None and lon is not None else ""
    c = db.get(SafetyContact, user.id)
    if c:
        try:
            if get_sms().send(c.phone, f"Dihari SOS: {user.name or user.phone} needs help.{where}"):
                notified.append("contact")
        except Exception:  # noqa: BLE001
            pass
    asg = db.scalar(select(Assignment).join(Job, Job.id == Assignment.job_id).where(
        Assignment.worker_id == user.id, Assignment.status == "confirmed",
        Job.status.in_([S.assigned.value, S.in_progress.value])).order_by(Job.start_at.desc()))
    if asg:
        notify(db, db.get(Job, asg.job_id).hirer_id, "sos", asg.job_id)
        notified.append("hirer")
    inc = Incident(user_id=user.id, assignment_id=asg.id if asg else None, lat=lat, lon=lon, notified=notified)
    db.add(inc)
    audit.log(db, user.id, "incident", user.id, "sos", data={"notified": notified})
    db.commit()
    return {"incident_id": inc.id, "notified": notified, "emergency_number": cfg.emergency_number,
            "has_contact": c is not None}


# ------------------------------------------------------------------ skills
def endorse(db: Session, hirer: User, worker_id: str, trade: str, years: int | None) -> Endorsement:
    cfg = get_country(hirer.country_code)
    if not cfg.trade(trade):
        raise DailyError("unknown_trade")
    worked = db.scalar(select(Assignment.id).join(Job, Job.id == Assignment.job_id).where(
        Assignment.worker_id == worker_id, Job.hirer_id == hirer.id, Assignment.status == "completed"))
    if not worked:
        raise DailyError("no_completed_job")
    e = db.scalar(select(Endorsement).where(Endorsement.worker_id == worker_id, Endorsement.trade == trade,
                                            Endorsement.endorsed_by == hirer.id))
    if e is None:
        e = Endorsement(worker_id=worker_id, trade=trade, endorsed_by=hirer.id)
        db.add(e)
    e.years = years
    audit.log(db, hirer.id, "endorsement", worker_id, "endorsed", data={"trade": trade, "years": years})
    db.commit()
    return e


def skills_of(db: Session, worker_id: str) -> list[dict]:
    rows = db.execute(select(Endorsement.trade, func.count(), func.max(Endorsement.years))
                      .where(Endorsement.worker_id == worker_id).group_by(Endorsement.trade)).all()
    return [{"trade": t, "endorsements": n, "years": y} for t, n, y in rows]


# ------------------------------------------------------------------ shareable Kaam Card
def card_token(user_id: str) -> str:
    sig = hmac.new(get_settings().secret_key.encode(), f"card:{user_id}".encode(), hashlib.sha256).hexdigest()[:12]
    return f"{user_id}-{sig}"


def card_user(db: Session, token: str) -> User | None:
    uid, _, sig = token.rpartition("-")
    if not uid or not hmac.compare_digest(card_token(uid), token):
        return None
    return db.get(User, uid)
