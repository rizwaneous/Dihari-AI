"""Notifications: web push first, SMS fallback, behind provider interfaces.
Real providers are added later (docs/PROVIDERS.md). `log` provider = in-app inbox (DB row)."""
import logging

import httpx
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Notification, PushSubscription, User
from ..settings import get_settings

log = logging.getLogger("dihari.notify")


class SmsProvider(Protocol):
    name: str
    def send(self, phone: str, text: str) -> bool: ...


class PushProvider(Protocol):
    name: str
    def send(self, db: Session, user: User, title: str, body: str) -> bool: ...


class StubSms:
    name = "stub"

    def __init__(self):
        self.outbox: list[tuple[str, str]] = []

    def send(self, phone: str, text: str) -> bool:
        self.outbox.append((phone, text))
        log.info("SMS(stub) to %s: %s", phone, text)
        return True


class TwilioSms:
    name = "twilio"

    def send(self, phone: str, text: str) -> bool:
        cfg = get_settings()
        if not all((cfg.twilio_account_sid, cfg.twilio_auth_token, cfg.twilio_from_number)):
            return False
        try:
            response = httpx.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{cfg.twilio_account_sid}/Messages.json",
                auth=(cfg.twilio_account_sid, cfg.twilio_auth_token),
                data={"To": phone, "From": cfg.twilio_from_number, "Body": text}, timeout=8)
            return response.is_success
        except httpx.HTTPError:
            return False


class InboxPush:
    """Delivers to the in-app inbox (polled by the PWA). Always succeeds."""
    name = "log"

    def send(self, db, user, title, body) -> bool:
        return True


_SMS: dict[str, type] = {"stub": StubSms, "twilio": TwilioSms}
_PUSH: dict[str, type] = {"log": InboxPush}
_instances: dict[tuple, object] = {}


def register_sms(name: str, factory) -> None:
    _SMS[name] = factory


def register_push(name: str, factory) -> None:
    _PUSH[name] = factory


def get_sms(name: str | None = None) -> SmsProvider:
    name = name or get_settings().sms_provider
    if ("sms", name) not in _instances:
        if name not in _SMS:
            raise RuntimeError(f"SMS provider '{name}' not registered (see docs/PROVIDERS.md)")
        _instances[("sms", name)] = _SMS[name]()
    return _instances[("sms", name)]


def get_push(name: str):
    if ("push", name) not in _instances:
        if name not in _PUSH:
            return None
        _instances[("push", name)] = _PUSH[name]()
    return _instances[("push", name)]


def notify(db: Session, user_id: str, title: str, body: str) -> str:
    """Try push providers in configured order, then SMS. Always leaves an inbox row. Returns channel used."""
    user = db.get(User, user_id)
    if not user:
        return "none"
    nearby_alert = title == "nearby_job"
    from .. import i18n
    tk = f"notify.{title}.title"
    if i18n.get_raw(tk, user.locale) is not None:  # `title` is a message key → localise per recipient
        title, body = i18n.t(tk, user.locale), i18n.t(f"notify.{title}.body", user.locale)
    has_sub = db.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id)).first() is not None
    channel = None
    for name in [n.strip() for n in get_settings().notify_providers.split(",") if n.strip()]:
        if name == "webpush" and has_sub and get_settings().vapid_private_key:
            channel = name
            break
        p = get_push(name)
        if p is None:
            continue
        if name != "log" and not has_sub:
            continue
        try:
            if p.send(db, user, title, body):
                channel = name
                break
        except Exception as e:  # noqa: BLE001
            log.warning("push provider %s failed: %s", name, e)
    if channel is None and nearby_alert:
        channel = "log"
    if channel is None:
        try:
            get_sms().send(user.phone, f"{title}: {body}")
            channel = "sms"
        except Exception as e:  # noqa: BLE001
            log.warning("sms fallback failed: %s", e)
            channel = "failed"
    db.add(Notification(user_id=user_id, channel=channel, title=title, body=body,
                        status={"webpush": "queued", "failed": "failed"}.get(channel, "sent")))
    return channel
