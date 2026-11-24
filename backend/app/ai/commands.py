"""Voice commands for people who cannot read: "mujhe aaj kaam chahiye" → open the job list.

Order: (1) keyword phrases from the locale file (`cmd.<action>` = phrases separated by "|"), checked in code;
(2) if nothing matched, the configured LLM chain picks one action from a closed list; (3) otherwise "unknown".
The AI only chooses which screen to open; it never performs money or booking actions itself."""
import json

from .. import i18n
from ..country_config import CountryConfig
from . import numbers as nm
from .base import AIUnavailable
from .chain import Chain

ACTIONS = {
    "worker": ["find_jobs", "set_available", "invites", "my_work", "check_in", "check_out", "hisaab", "kaam_card", "sos", "help"],
    "hirer": ["post_job", "free_workers", "my_jobs", "team", "hisaab", "sos", "help"],
}
SYSTEM = ("You route a short spoken request from a daily-wage worker or a hirer to ONE app action. "
          "Reply JSON {\"action\": <one of the allowed actions or \"unknown\">}.")


def _phrases(action: str, lang: str) -> list[str]:
    out = []
    for lg in dict.fromkeys([lang, *i18n.available()]):
        raw = i18n.get_raw(f"cmd.{action}", lg)
        if isinstance(raw, str):
            out += [p.strip().lower() for p in raw.split("|") if p.strip()]
    return out


def route(text: str, role: str, cfg: CountryConfig, lang: str, chain: Chain | None = None) -> dict:
    t = nm.norm(text or "").lower()
    allowed = ACTIONS.get(role, [])
    best, best_len = None, 0
    for a in allowed:
        for p in _phrases(a, lang):
            if p and p in t and len(p) > best_len:
                best, best_len = a, len(p)
    source = "rules"
    if best is None and role == "hirer" and cfg.find_trade(t):
        best = "post_job"          # "2 mistri chahiye kal G-13" is a job post
    if best is None and chain is not None and chain.has_real:
        try:
            r, _ = chain.call("complete_json", task="route_command", system=SYSTEM,
                              prompt=json.dumps({"text": text, "role": role, "allowed_actions": allowed}, ensure_ascii=False),
                              schema={"type": "object", "properties": {"action": {"type": "string"}}, "required": ["action"]})
            if r.get("action") in allowed:
                best, source = r["action"], "ai"
        except AIUnavailable:
            pass
    action = best or "unknown"
    return {"action": action, "source": source, "text": text,
            "say": i18n.t(f"cmd.say.{action}", lang)}
