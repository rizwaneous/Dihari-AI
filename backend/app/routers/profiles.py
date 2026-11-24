from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, need_role
from ..models import HirerProfile, User, WorkerProfile
from ..modules import profiles

router = APIRouter(prefix="/profiles", tags=["profiles"])


class WorkerIn(BaseModel):
    name: str | None = None
    trades: list[str] | None = None
    area_name: str | None = None
    lat: float | None = None
    lon: float | None = None
    radius_km: float | None = None


class HirerIn(BaseModel):
    name: str | None = None
    hirer_type: str | None = None


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = {"id": user.id, "phone": user.phone, "role": user.role, "name": user.name,
           "country": user.country_code, "locale": user.locale}
    from ..models import SafetyContact
    from ..modules import daily
    sc = db.get(SafetyContact, user.id)
    out["safety_contact"] = sc and {"name": sc.name, "phone": sc.phone}
    if user.role == "worker":
        p = db.get(WorkerProfile, user.id)
        out["profile"] = p and {"trades": p.trades, "area_name": p.area_name, "lat": p.lat, "lon": p.lon, "radius_km": p.radius_km}
        out["available_today"] = daily.is_available(db, user.id)
    else:
        p = db.get(HirerProfile, user.id)
        out["profile"] = p and {"hirer_type": p.hirer_type}
    return out


@router.put("/worker")
def put_worker(body: WorkerIn, user: User = Depends(need_role("worker")), db: Session = Depends(get_db)):
    try:
        p = profiles.upsert_worker(db, user, **body.model_dump())
    except profiles.ProfileError as e:
        raise HTTPException(400, str(e))
    return {"trades": p.trades, "area_name": p.area_name, "lat": p.lat, "lon": p.lon, "radius_km": p.radius_km}


@router.put("/hirer")
def put_hirer(body: HirerIn, user: User = Depends(need_role("hirer")), db: Session = Depends(get_db)):
    try:
        p = profiles.upsert_hirer(db, user, **body.model_dump())
    except profiles.ProfileError as e:
        raise HTTPException(400, str(e))
    return {"hirer_type": p.hirer_type}
