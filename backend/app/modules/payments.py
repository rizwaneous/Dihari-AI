"""Job execution + payment-day check-ins. Payment status is SELF-REPORTED; no money moves here."""
import asyncio
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..country_config import get_country
from ..db import SessionLocal, utcnow
from ..models import Assignment, Job, JobStatus as S, PaymentCheckin, User
from ..settings import get_settings
from . import audit, cases, jobs
from .notifications import notify

log = logging.getLogger("dihari.payments")


class PaymentError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _local_date(job: Job, now: datetime) -> date:
    return now.astimezone(ZoneInfo(get_country(job.country_code).timezone)).date()


def start_job(db: Session, job: Job, actor: User) -> Job:
    if job.hirer_id != actor.id:
        raise PaymentError("forbidden")
    jobs.lock_for_booking(db, job)
    confirmed = db.scalars(select(Assignment).where(Assignment.job_id == job.id, Assignment.status == "confirmed")).all()
    if not confirmed:
        raise PaymentError("no_confirmed_workers")
    jobs.transition(db, job, S.in_progress, actor.id)
    db.commit()
    return job


def complete_job(db: Session, job: Job, actor: User, absent: list[str] | None = None) -> Job:
    if job.hirer_id != actor.id:
        raise PaymentError("forbidden")
    absent = set(absent or [])
    jobs.transition(db, job, S.completed, actor.id)
    for asg in db.scalars(select(Assignment).where(Assignment.job_id == job.id, Assignment.status == "confirmed")):
        asg.status = "no_show" if asg.id in absent else "completed"
        audit.log(db, actor.id, "assignment", asg.id, asg.status, "confirmed", asg.status)
        if asg.status == "completed":
            for party, uid in (("worker", asg.worker_id), ("hirer", job.hirer_id)):
                db.add(PaymentCheckin(assignment_id=asg.id, user_id=uid, party=party, due_on=job.payment_day))
    db.commit()
    return job


def send_due_reminders(db: Session, now: datetime | None = None) -> int:
    """Scheduled job: reminders to BOTH parties on payment day. Idempotent."""
    now = now or utcnow()
    n = 0
    for ck in db.scalars(select(PaymentCheckin).where(PaymentCheckin.reminded_at.is_(None), PaymentCheckin.answered_at.is_(None))):
        asg = db.get(Assignment, ck.assignment_id)
        job = db.get(Job, asg.job_id)
        if _local_date(job, now) >= ck.due_on:
            notify(db, ck.user_id, f"payment_checkin_{ck.party}", asg.id)
            ck.reminded_at = now
            n += 1
    db.commit()
    return n


def report_payment(db: Session, asg: Assignment, worker: User, status: str, now: datetime | None = None) -> Assignment:
    now = now or utcnow()
    if asg.worker_id != worker.id:
        raise PaymentError("forbidden")
    if status not in ("paid", "unpaid"):
        raise PaymentError("bad_status")
    if asg.status != "completed":
        raise PaymentError("not_completed")
    job = db.get(Job, asg.job_id)
    if status == "unpaid" and _local_date(job, now) < job.payment_day:
        raise PaymentError("not_due_yet")
    asg.payment_report, asg.payment_reported_at = status, now
    for ck in db.scalars(select(PaymentCheckin).where(PaymentCheckin.assignment_id == asg.id, PaymentCheckin.party == "worker")):
        ck.answered_at = now
    audit.log(db, worker.id, "assignment", asg.id, f"payment_{status}")
    siblings = db.scalars(select(Assignment).where(Assignment.job_id == job.id, Assignment.status == "completed")).all()
    if status == "unpaid":
        cases.open_case(db, asg, job)
        if job.status == S.completed.value:
            jobs.transition(db, job, S.disputed, worker.id, {"assignment": asg.id})
        notify(db, job.hirer_id, "payment_reported_unpaid", job.id)
    elif all(a.payment_report == "paid" for a in siblings) and job.status in (S.completed.value, S.disputed.value):
        if job.status == S.completed.value or not any(a.payment_report == "unpaid" for a in siblings):
            jobs.transition(db, job, S.payment_confirmed, worker.id)
    db.commit()
    return asg


def hirer_claim(db: Session, asg: Assignment, hirer: User, status: str, now: datetime | None = None) -> Assignment:
    job = db.get(Job, asg.job_id)
    if job.hirer_id != hirer.id:
        raise PaymentError("forbidden")
    if status not in ("paid", "not_yet"):
        raise PaymentError("bad_status")
    asg.hirer_payment_claim = status
    for ck in db.scalars(select(PaymentCheckin).where(PaymentCheckin.assignment_id == asg.id, PaymentCheckin.party == "hirer")):
        ck.answered_at = now or utcnow()
    audit.log(db, hirer.id, "assignment", asg.id, f"hirer_claim_{status}")
    db.commit()
    return asg


def rate_worker(db: Session, asg: Assignment, hirer: User, stars: int) -> Assignment:
    job = db.get(Job, asg.job_id)
    if job.hirer_id != hirer.id or asg.status != "completed":
        raise PaymentError("forbidden")
    if not 1 <= stars <= 5:
        raise PaymentError("bad_rating")
    asg.rating = stars
    audit.log(db, hirer.id, "assignment", asg.id, "rated", data={"stars": stars})
    db.commit()
    return asg


async def scheduler_loop():
    while True:
        try:
            with SessionLocal() as db:
                send_due_reminders(db)
        except Exception:  # noqa: BLE001
            log.exception("scheduler tick failed")
        await asyncio.sleep(get_settings().scheduler_interval_seconds)
