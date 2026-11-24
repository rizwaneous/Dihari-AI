"""Deliver committed Web Push inbox entries. A transaction claims each batch on Postgres."""
import asyncio
import json
import logging
from urllib.parse import urlsplit

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Notification, PushSubscription
from ..settings import get_settings

log = logging.getLogger(__name__)


def valid_endpoint(endpoint):
    try:
        url = urlsplit(endpoint)
        host = url.hostname or ""
        port = url.port
    except ValueError:
        return False
    return (url.scheme == "https" and url.username is None and url.password is None
            and port in (None, 443) and bool(url.path.strip("/"))
            and (host in ("fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com")
                 or host.endswith(".notify.windows.com") or host.endswith(".push.apple.com")))


def deliver_batch():
    from pywebpush import WebPushException, webpush
    settings = get_settings()
    with SessionLocal() as db:
        rows = db.scalars(select(Notification).where(Notification.channel == "webpush",
                          Notification.status.in_(["queued", "retry1", "retry2", "retry3"])).order_by(Notification.status, Notification.created_at)
                          .limit(20).with_for_update(skip_locked=True)).all()
        for row in rows:
            subs = db.scalars(select(PushSubscription).where(PushSubscription.user_id == row.user_id)).all()
            retry = False
            sent = False
            for sub in subs:
                if not valid_endpoint(sub.endpoint):
                    continue
                try:
                    webpush(subscription_info={"endpoint": sub.endpoint, "keys": sub.keys},
                            data=json.dumps({"title": row.title, "body": row.body, "tag": row.id}),
                            vapid_private_key=settings.vapid_private_key,
                            vapid_claims={"sub": settings.vapid_subject}, timeout=5, ttl=120)
                    sent = True
                except WebPushException as exc:
                    code = getattr(exc.response, "status_code", None)
                    if code in (404, 410):
                        db.delete(sub)
                    elif code is None or code == 429 or code >= 500:
                        retry = True
                    else:
                        log.warning("Push delivery rejected with status %s", code)
            if retry:
                row.status = {"queued": "retry1", "retry1": "retry2", "retry2": "retry3", "retry3": "failed"}[row.status]
            else:
                row.status = "sent" if sent else "skipped"
        db.commit()


async def run_delivery():
    while True:
        try:
            await asyncio.to_thread(deliver_batch)
        except Exception:
            log.warning("Push batch failed; will retry")
        await asyncio.sleep(10)
