from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..settings import get_settings
from ..modules.delivery import valid_endpoint
from ..models import Notification, PushSubscription, User

router = APIRouter(prefix="/notifications", tags=["notifications"])


class SubIn(BaseModel):
    endpoint: str
    keys: dict = {}


@router.get("")
def inbox(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(50))
    return [{"id": n.id, "title": n.title, "body": n.body, "channel": n.channel, "at": n.created_at.isoformat()} for n in rows]


@router.get("/config")
def push_config():
    cfg = get_settings()
    enabled = "webpush" in cfg.notify_providers.split(",") and cfg.vapid_private_key and cfg.vapid_subject
    return {"public_key": cfg.vapid_public_key if enabled else ""}


@router.post("/unsubscribe")
def unsubscribe(body: SubIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    for sub in db.scalars(select(PushSubscription).where(PushSubscription.user_id == user.id,
                                                          PushSubscription.endpoint == body.endpoint)):
        db.delete(sub)
    db.commit()
    return {"ok": True}


@router.post("/subscribe", status_code=201)
def subscribe(body: SubIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if push_config()["public_key"] and (not valid_endpoint(body.endpoint) or not all(body.keys.get(k) for k in ("auth", "p256dh"))):
        raise HTTPException(400, "invalid_subscription")
    if not db.scalars(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)).first():
        db.add(PushSubscription(user_id=user.id, endpoint=body.endpoint, keys=body.keys))
        db.commit()
    return {"ok": True}
