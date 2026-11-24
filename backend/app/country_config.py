"""Country configuration loader. Adding a country = adding a JSON file; no code change."""
import json
import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from .settings import get_settings


class Currency(BaseModel):
    code: str
    symbol: str = ""
    minor_units: int = 0


class PhoneCfg(BaseModel):
    dial_code: str
    national_regex: str
    strip_leading_zero: bool = True
    example: str = ""


class Region(BaseModel):
    code: str
    name: dict[str, str] = {}
    aliases: list[str] = []
    patterns: list[str] = []
    bbox: list[float] | None = None  # [min_lat, min_lon, max_lat, max_lon]


class Trade(BaseModel):
    code: str
    icon: str = "🛠️"
    names: dict[str, str] = {}
    aliases: list[str] = []
    generic: bool = False   # fallback trade; loses to any specific trade match


class Place(BaseModel):
    name: str
    aliases: list[str] = []
    region: str
    lat: float
    lon: float
    approx: bool = False


class Holiday(BaseModel):
    date: str
    name: dict[str, str] = {}


class CountryConfig(BaseModel):
    code: str
    name: dict[str, str] = {}
    timezone: str = "UTC"
    currency: Currency
    phone: PhoneCfg
    languages: list[str]
    default_language: str
    demo_only: bool = False
    wage_rules_file: str
    default_radius_km: float = 10
    max_radius_km: float = 40
    max_counter_multiple: float = 2.0
    rate_step: int = 50
    asr_providers: list[str] = ["mock"]
    tts_providers: list[str] = ["mock"]
    asr_language_hints: dict[str, str] = {}
    regions: list[Region]
    default_region: str
    trades: list[Trade] = []
    places: list[Place] = []
    holidays: list[Holiday] = []
    emergency_number: str | None = None     # shown on the safety screen
    late_cancel_hours: int = 12             # a hirer cancelling closer than this to the start owes a fee
    late_cancel_fee: int = 0                # per booked worker, in whole currency units
    urgent_radius_km: float = 3             # "needed now" posts ping free workers this close

    # -- phone ---------------------------------------------------------
    def normalize_phone(self, raw: str) -> str | None:
        s = re.sub(r"[\s\-()]", "", raw or "")
        dial = self.phone.dial_code
        if s.startswith("+"):
            if not s.startswith(dial):
                return None
            national = s[len(dial):]
        elif s.startswith(dial.lstrip("+")) and len(s) > len(dial) - 1 + 5:
            national = s[len(dial) - 1:]
        else:
            national = s
        if self.phone.strip_leading_zero:
            national = national.lstrip("0") if national.startswith("0") else national
        if not re.fullmatch(self.phone.national_regex, national):
            return None
        return f"{dial}{national}"

    # -- regions / places ----------------------------------------------
    def region_by_code(self, code: str) -> Region | None:
        return next((r for r in self.regions if r.code == code), None)

    def resolve_region(self, text: str | None = None, lat: float | None = None, lon: float | None = None) -> str:
        t = (text or "").strip().lower()
        if t:
            place = self.find_place(t)
            if place:
                return place.region
            for r in self.regions:
                if any(a.lower() in t for a in r.aliases) or any(re.search(p, t) for p in r.patterns):
                    return r.code
        if lat is not None and lon is not None:
            for r in self.regions:
                if r.bbox and r.bbox[0] <= lat <= r.bbox[2] and r.bbox[1] <= lon <= r.bbox[3]:
                    return r.code
        return self.default_region

    def find_place(self, text: str) -> Place | None:
        t = text.strip().lower()
        for p in self.places:
            names = [p.name.lower(), *[a.lower() for a in p.aliases]]
            if any(n and n in t for n in names):
                return p
        return None

    def find_trade(self, text: str) -> Trade | None:
        t = text.lower()
        best, best_key = None, (-1, 0)
        for tr in self.trades:
            for a in [tr.code, *tr.aliases]:
                key = (0 if tr.generic else 1, len(a))
                if a.lower() in t and key > best_key:
                    best, best_key = tr, key
        return best

    def trade(self, code: str) -> Trade | None:
        return next((t for t in self.trades if t.code == code), None)


class CountryRegistry:
    def __init__(self, directory: str | Path, include_demo: bool = False):
        self.dir = Path(directory)
        self._cache: dict[str, CountryConfig] = {}
        for f in sorted((self.dir / "countries").glob("*.json")):
            cfg = CountryConfig(**json.loads(f.read_text(encoding="utf-8")))
            if include_demo or not cfg.demo_only:
                self._cache[cfg.code] = cfg

    def codes(self) -> list[str]:
        return list(self._cache)

    def get(self, code: str) -> CountryConfig:
        if code not in self._cache:
            raise KeyError(f"unknown country {code}")
        return self._cache[code]

    def wage_rules_path(self, code: str) -> Path:
        return self.dir / self.get(code).wage_rules_file

    def detect_by_phone(self, raw: str) -> tuple[CountryConfig, str] | None:
        for cfg in self._cache.values():
            n = cfg.normalize_phone(raw)
            if n:
                return cfg, n
        return None


@lru_cache
def _registry(path: str, include_demo: bool) -> CountryRegistry:
    return CountryRegistry(path, include_demo)


def registry(path: str | None = None) -> CountryRegistry:
    return _registry(path or get_settings().config_dir, get_settings().dev_mode)


def get_country(code: str | None = None) -> CountryConfig:
    return registry().get(code or get_settings().default_country)
