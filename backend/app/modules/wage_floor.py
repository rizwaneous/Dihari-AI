"""Wage floor. PURE CODE — no LLM, no network. Reads versioned rules per country/region."""
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .. import i18n
from ..country_config import registry


@dataclass
class Rule:
    region: str
    version: str
    effective_date: date
    currency: str
    min_daily_wage: int
    max_hours_per_day: float
    max_payment_delay_days: int
    source_url: str | None
    verified: bool
    placeholder: bool = False


@dataclass
class Violation:
    code: str
    params: dict = field(default_factory=dict)

    def message(self, lang: str) -> str:
        params = dict(self.params)
        if "currency" in params:
            params["currency"] = i18n.t(f"currency.{params['currency']}", lang) if i18n.get_raw(
                f"currency.{params['currency']}", lang) else params["currency"]
        return i18n.t(f"violation.{self.code}", lang, **params)


@dataclass
class WageCheck:
    ok: bool
    violations: list[Violation]
    rule: Rule | None
    warnings: list[str]

    def explain(self, lang: str = "ur") -> list[str]:
        out = [v.message(lang) for v in self.violations]
        out += [i18n.t(f"warning.{w}", lang) for w in self.warnings]
        return out

    def to_dict(self, lang: str = "ur") -> dict:
        return {"ok": self.ok,
                "violations": [{"code": v.code, "params": v.params, "message": v.message(lang)} for v in self.violations],
                "warnings": [{"code": w, "message": i18n.t(f"warning.{w}", lang)} for w in self.warnings],
                "rule": self.rule and {"region": self.rule.region, "version": self.rule.version,
                                       "min_daily_wage": self.rule.min_daily_wage,
                                       "max_hours_per_day": self.rule.max_hours_per_day,
                                       "currency": self.rule.currency, "verified": self.rule.verified,
                                       "source_url": self.rule.source_url}}


def load_rules(country: str, path: Path | None = None) -> list[Rule]:
    p = path or registry().wage_rules_path(country)
    raw = json.loads(Path(p).read_text(encoding="utf-8"))
    return [Rule(region=r["region"], version=r["version"], effective_date=date.fromisoformat(r["effective_date"]),
                 currency=r["currency"], min_daily_wage=int(r["min_daily_wage"]),
                 max_hours_per_day=float(r["max_hours_per_day"]),
                 max_payment_delay_days=int(r.get("max_payment_delay_days", 7)),
                 source_url=r.get("source_url"), verified=bool(r.get("verified", False)),
                 placeholder=bool(r.get("placeholder", False))) for r in raw["rules"]]


def find_rule(country: str, region: str, on: date, rules: list[Rule] | None = None) -> Rule | None:
    rules = rules if rules is not None else load_rules(country)
    for reg in (region, "*"):
        cands = [r for r in rules if r.region == reg and r.effective_date <= on]
        if cands:
            return max(cands, key=lambda r: r.effective_date)
    return None


def check(*, country: str, region: str, daily_rate: int | None, hours_per_day: float | None,
          payment_day: date | None, start_date: date | None, days: int = 1,
          deductions: list[dict] | None = None, on: date | None = None,
          rules: list[Rule] | None = None) -> WageCheck:
    on = on or date.today()
    rule = find_rule(country, region, on, rules)
    v: list[Violation] = []
    warnings: list[str] = []
    if rule is None:
        return WageCheck(False, [Violation("no_rule")], None, [])
    if not rule.verified:
        warnings.append("unverified_rule")

    if daily_rate is not None and daily_rate < rule.min_daily_wage:
        v.append(Violation("below_min_wage", {"min": rule.min_daily_wage, "currency": rule.currency}))
    if hours_per_day is not None and hours_per_day > rule.max_hours_per_day:
        v.append(Violation("hours_exceed_max", {"hours": _n(hours_per_day), "max": _n(rule.max_hours_per_day)}))

    total_ded = 0
    for d in deductions or []:
        amt = d.get("amount") if isinstance(d, dict) else None
        try:
            amt = None if amt is None else int(amt)
        except (TypeError, ValueError):
            amt = None
        if amt is None or amt < 0:
            v.append(Violation("hidden_deduction", {"label": (d.get("label") if isinstance(d, dict) else None) or "?"}))
        else:
            total_ded += amt
    if daily_rate is not None and total_ded and not any(x.code == "below_min_wage" for x in v):
        net = daily_rate - total_ded / max(days, 1)
        if net < rule.min_daily_wage:
            v.append(Violation("net_below_min_wage", {"net": int(net), "min": rule.min_daily_wage, "currency": rule.currency}))

    if payment_day is None:
        v.append(Violation("missing_payment_day"))
    elif start_date is not None:
        if payment_day < start_date:
            v.append(Violation("payment_before_start"))
        last_work_day = start_date + timedelta(days=max(days, 1) - 1)
        if (payment_day - last_work_day).days > rule.max_payment_delay_days:
            v.append(Violation("payment_too_late", {"max": rule.max_payment_delay_days}))
    return WageCheck(not v, v, rule, warnings)


def _n(x: float):
    return int(x) if float(x).is_integer() else x
