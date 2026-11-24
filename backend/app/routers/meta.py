from fastapi import APIRouter, HTTPException

from .. import i18n
from ..country_config import registry
from ..settings import get_settings

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/countries")
def countries():
    return [{"code": c, "name": registry().get(c).name} for c in registry().codes()]


@router.get("/country/{code}")
def country(code: str):
    try:
        c = registry().get(code)
    except KeyError:
        raise HTTPException(404, "unknown country")
    d = c.model_dump(exclude={"wage_rules_file", "holidays"})
    d["places"] = [{"name": p.name, "region": p.region, "lat": p.lat, "lon": p.lon} for p in c.places]
    return d


@router.get("/default-country")
def default_country():
    return {"code": get_settings().default_country}


@router.get("/locale/{lang}")
def locale(lang: str):
    if lang not in i18n.available():
        raise HTTPException(404, "unknown locale")
    return i18n._load(get_settings().locales_dir, lang)


@router.get("/locales")
def locales():
    return [{"code": l, **i18n.meta(l)} for l in i18n.available()]
