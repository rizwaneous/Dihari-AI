import enum
import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, UTCDateTime, utcnow


def _id() -> str:
    return uuid.uuid4().hex


class JobStatus(str, enum.Enum):
    open = "open"
    offers = "offers"
    assigned = "assigned"
    in_progress = "in_progress"
    completed = "completed"
    payment_confirmed = "payment_confirmed"
    disputed = "disputed"
    cancelled = "cancelled"


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # E.164
    country_code: Mapped[str] = mapped_column(String(4))
    role: Mapped[str] = mapped_column(String(10), default="worker")  # worker | hirer
    locale: Mapped[str] = mapped_column(String(8), default="ur")
    name: Mapped[str | None] = mapped_column(String(80))
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class OtpCode(Base):
    __tablename__ = "otp_codes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class WorkerProfile(Base):
    __tablename__ = "worker_profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    trades: Mapped[list] = mapped_column(JSON, default=list)
    area_name: Mapped[str | None] = mapped_column(String(80))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    radius_km: Mapped[float] = mapped_column(Float, default=10)


class HirerProfile(Base):
    __tablename__ = "hirer_profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    hirer_type: Mapped[str] = mapped_column(String(12), default="household")  # household|contractor|business
    posting_restricted: Mapped[bool] = mapped_column(Boolean, default=False)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    hirer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    country_code: Mapped[str] = mapped_column(String(4))
    region: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.open.value, index=True)
    task: Mapped[str] = mapped_column(String(40))  # trade code
    headcount: Mapped[int] = mapped_column(Integer)
    location_text: Mapped[str] = mapped_column(String(120))
    address_detail: Mapped[str | None] = mapped_column(String(200))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    start_at: Mapped[datetime] = mapped_column(UTCDateTime)
    days: Mapped[int] = mapped_column(Integer, default=1)
    daily_rate: Mapped[int] = mapped_column(Integer)
    hours_per_day: Mapped[float] = mapped_column(Float)
    payment_day: Mapped[date] = mapped_column(Date)
    advance: Mapped[int] = mapped_column(Integer, default=0)
    deductions: Mapped[list] = mapped_column(JSON, default=list)  # [{label, amount}]
    transport_mode: Mapped[str] = mapped_column(String(12), default="none")
    transport_amount: Mapped[int | None] = mapped_column(Integer)
    transcript: Mapped[str | None] = mapped_column(Text)
    readback_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    rule_version: Mapped[str | None] = mapped_column(String(40))
    rule_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)   # "Abhi chahiye": same-day, pinged to free workers nearby
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Offer(Base):
    __tablename__ = "offers"
    __table_args__ = (UniqueConstraint("job_id", "worker_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    worker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    rate: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(10))  # accept | counter
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|selected|rejected|withdrawn
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Agreement(Base):
    """Immutable snapshot of agreed terms. Updates and deletes are blocked at ORM level."""
    __tablename__ = "agreements"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    worker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    hirer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    terms: Mapped[dict] = mapped_column(JSON)
    terms_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


@event.listens_for(Agreement, "before_update")
def _agreement_no_update(mapper, connection, target):
    raise ValueError("agreements are immutable")


@event.listens_for(Agreement, "before_delete")
def _agreement_no_delete(mapper, connection, target):
    raise ValueError("agreements are immutable")


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("job_id", "worker_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    worker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    agreement_id: Mapped[str] = mapped_column(ForeignKey("agreements.id"))
    status: Mapped[str] = mapped_column(String(12), default="assigned")  # assigned|confirmed|completed|no_show|cancelled
    worker_confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    payment_report: Mapped[str | None] = mapped_column(String(8))  # paid | unpaid (worker, self-reported)
    payment_reported_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    hirer_payment_claim: Mapped[str | None] = mapped_column(String(8))  # paid | not_yet
    rating: Mapped[int | None] = mapped_column(Integer)  # hirer -> worker, 1..5


class PaymentCheckin(Base):
    __tablename__ = "payment_checkins"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    party: Mapped[str] = mapped_column(String(8))  # worker | hirer
    due_on: Mapped[date] = mapped_column(Date)
    reminded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id"), unique=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    hirer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    worker_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(20), default="unpaid")
    status: Mapped[str] = mapped_column(String(12), default="open")  # open|closed
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    actions = relationship("CaseAction", back_populates="case")


class Reviewer(Base):
    __tablename__ = "reviewers"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CaseAction(Base):
    __tablename__ = "case_actions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(30))  # remind_hirer|request_hirer_response|restrict_hirer_posting|close_no_action
    status: Mapped[str] = mapped_column(String(10), default="proposed")  # proposed|approved|rejected
    proposed_by: Mapped[str] = mapped_column(String(20), default="rules")
    reviewer_name: Mapped[str | None] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    case = relationship("Case", back_populates="actions")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    actor: Mapped[str] = mapped_column(String(40))
    entity: Mapped[str] = mapped_column(String(30), index=True)
    entity_id: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[str] = mapped_column(String(40))
    from_state: Mapped[str | None] = mapped_column(String(30))
    to_state: Mapped[str | None] = mapped_column(String(30))
    data: Mapped[dict | None] = mapped_column(JSON)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    reporter_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    target_type: Mapped[str] = mapped_column(String(10))  # job | user
    target_id: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    channel: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="sent")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    endpoint: Mapped[str] = mapped_column(Text)
    keys: Mapped[dict] = mapped_column(JSON, default=dict)


class AICallLog(Base):
    __tablename__ = "ai_call_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    kind: Mapped[str] = mapped_column(String(10))
    provider: Mapped[str] = mapped_column(String(40))
    ok: Mapped[bool] = mapped_column(Boolean)
    latency_ms: Mapped[int] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------- Round 2: practical features
class Availability(Base):
    """'Aaj farigh hoon': a worker is free today. Expires at the end of the local day."""
    __tablename__ = "availability"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    until: Mapped[datetime] = mapped_column(UTCDateTime)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Invite(Base):
    """A hirer asks a specific (free) worker to take a job. The worker accepts by booking it."""
    __tablename__ = "invites"
    __table_args__ = (UniqueConstraint("job_id", "worker_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    worker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    hirer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(10), default="pending")   # pending|accepted|declined
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Attendance(Base):
    """Site check-in / check-out, one row per assignment per local day."""
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("assignment_id", "day"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    check_in_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    check_out_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    distance_m: Mapped[int | None] = mapped_column(Integer)          # from the job site at check-in
    marked_by: Mapped[str] = mapped_column(String(8), default="worker")   # worker | hirer (thekedar marks for his team)


class LedgerEntry(Base):
    """Hisaab: money that moved (or is owed) on one assignment. Rows are never edited, only confirmed."""
    __tablename__ = "ledger_entries"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))      # advance | kharchi | payment | deduction | cancellation_fee
    amount: Mapped[int] = mapped_column(Integer)
    method: Mapped[str | None] = mapped_column(String(12))   # cash | jazzcash | easypaisa | bank
    reference: Mapped[str | None] = mapped_column(String(40))   # transaction id = proof
    note: Mapped[str | None] = mapped_column(String(120))
    created_by: Mapped[str] = mapped_column(String(40))   # user id or "system"
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Team(Base):
    """A thekedar's crew."""
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class TeamMember(Base):
    __tablename__ = "team_members"
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    worker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class SafetyContact(Base):
    __tablename__ = "safety_contacts"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    phone: Mapped[str] = mapped_column(String(20))


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    assignment_id: Mapped[str | None] = mapped_column(String(32))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    notified: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Endorsement(Base):
    """A hirer who completed a job with a worker vouches for a skill ("Tile: 3 years")."""
    __tablename__ = "endorsements"
    __table_args__ = (UniqueConstraint("worker_id", "trade", "endorsed_by"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    worker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    trade: Mapped[str] = mapped_column(String(40))
    years: Mapped[int | None] = mapped_column(Integer)
    endorsed_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
