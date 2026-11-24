"""Adding a country or language = config + locale files only. Proven with a dummy country ZZ and dummy locale zz."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app import i18n
from app.ai import pipeline, service
from app.country_config import get_country, registry
from app.modules import wage_floor
from app.settings import get_settings

APP = Path(__file__).resolve().parents[1] / "app"
NOW = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def zz(tmp_path, monkeypatch):
    cfgd, locd = tmp_path / "config", tmp_path / "locales"
    (cfgd / "countries").mkdir(parents=True); (cfgd / "wage_rules").mkdir(); locd.mkdir()
    (cfgd / "countries" / "zz.json").write_text(json.dumps({
        "code": "ZZ", "name": {"en": "Zedland"}, "timezone": "UTC", "currency": {"code": "ZED", "symbol": "Z"},
        "phone": {"dial_code": "+999", "national_regex": "^\\d{7}$", "strip_leading_zero": False},
        "languages": ["zz", "en"], "default_language": "zz", "wage_rules_file": "wage_rules/zz.json",
        "regions": [{"code": "NORTH", "aliases": ["northton"], "bbox": [10, 10, 20, 20]}], "default_region": "NORTH",
        "trades": [{"code": "tile", "aliases": ["tegel"]}],
        "places": [{"name": "Alpha Park", "aliases": ["alpha"], "region": "NORTH", "lat": 12.0, "lon": 12.0}]}))
    (cfgd / "wage_rules" / "zz.json").write_text(json.dumps({"country_code": "ZZ", "rules": [
        {"region": "*", "version": "z1", "effective_date": "2020-01-01", "currency": "ZED", "min_daily_wage": 500,
         "max_hours_per_day": 6, "verified": True, "source_url": "http://example.invalid"}]}))
    (locd / "zz.json").write_text(json.dumps({"_meta": {"name": "Zorbish", "dir": "ltr"},
        "readback.job": "ZORB {headcount}/{task}/{location}/{rate}{currency}", "currency.ZED": "zeds",
        "violation.below_min_wage": "ZORB below {min} {currency}"}))
    (locd / "en.json").write_text((Path(get_settings().locales_dir) / "en.json").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("CONFIG_DIR", str(cfgd)); monkeypatch.setenv("LOCALES_DIR", str(locd))
    monkeypatch.setenv("DEFAULT_COUNTRY", "ZZ")
    get_settings.cache_clear(); service.reset()
    yield
    get_settings.cache_clear(); service.reset()


def test_new_country_phone_region_and_floor(zz):
    c = get_country("ZZ")
    assert c.normalize_phone("+9991234567") == "+9991234567" and c.normalize_phone("+923001234567") is None
    assert c.resolve_region("northton") == "NORTH" and c.resolve_region(None, 15, 15) == "NORTH"
    r = wage_floor.check(country="ZZ", region="NORTH", daily_rate=400, hours_per_day=8, payment_day=None, start_date=None,
                         on=NOW.date())
    assert {v.code for v in r.violations} >= {"below_min_wage", "hours_exceed_max"} and not r.warnings  # verified rule
    assert "ZORB below 500 zeds" in r.violations[0].message("zz")
    assert "zz" in i18n.available() and i18n.t("app.name", "zz") == "Dihari"  # falls back to en


def test_new_country_full_voice_pipeline_with_new_locale(zz):
    d = pipeline.draft_from_text("two workers tomorrow 9am tegel in alpha park 800 a day 6 hours pay same day "
                                 "no deductions no advance no transport", get_country("ZZ"), "zz", None, NOW)
    assert d["ready"], (d["missing"], d["invalid"])
    assert d["readback"] == "ZORB 2/tile/Alpha Park/800zeds"
    assert d["wage"]["rule"]["verified"] is True


def test_no_hardcoded_country_in_logic():
    bad = re.compile(r"Pakistan|PKR|\+92")
    offenders = [f"{p.relative_to(APP)}:{i}" for p in APP.rglob("*.py")
                 for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if bad.search(line)]
    assert offenders == []
