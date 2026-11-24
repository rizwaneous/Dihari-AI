"""Google Gemini provider: the AI "brain" for the prototype.

One API key (GEMINI_API_KEY) powers three things:
  * LLM  "gemini"      → job extraction (speech text → structured job fields)
  * ASR  "gemini"      → Urdu speech-to-text (audio sent to a multimodal Gemini model)
  * TTS  "gemini"      → Urdu read-aloud (Gemini TTS model, returns WAV)

Each kind tries a short list of models in order (GEMINI_*_MODELS) because single models are sometimes
overloaded (HTTP 503). If every model fails, the chain falls through to the next provider (normally `mock`),
so the app keeps working offline.

Select it in backend/.env with ASR_PROVIDERS=gemini,mock (and TTS_/LLM_EXTRACT_PROVIDERS). Without a key every
call fails fast and the chain falls back to the next provider.
"""
import base64
import json
import logging
import re
import struct
import time

import httpx

from ...settings import get_settings
from .. import registry
from ..base import Audio, Transcript

log = logging.getLogger("dihari.ai.gemini")
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
LANG_NAMES = {"ur": "Urdu", "en": "English", "pa": "Punjabi", "ps": "Pashto", "sd": "Sindhi", "ar": "Arabic"}


class GeminiError(RuntimeError):
    pass


def _models(csv: str) -> list[str]:
    return [m.strip() for m in csv.split(",") if m.strip()]


def _post(model: str, body: dict, timeout: float) -> dict:
    s = get_settings()
    if not s.gemini_api_key:
        raise GeminiError("GEMINI_API_KEY is not set")
    r = httpx.post(API.format(model=model), json=body, timeout=timeout,
                   headers={"x-goog-api-key": s.gemini_api_key, "content-type": "application/json"})
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", "")
        except ValueError:
            msg = r.text[:200]
        raise GeminiError(f"{model}: HTTP {r.status_code} {msg[:160]}")
    return r.json()


def generate(models: list[str], body: dict, *, timeout: float | None = None, attempts: int = 2) -> tuple[dict, str]:
    """POST to the first model that answers. Overloaded (429/5xx) and timeouts move on to the next model."""
    timeout = timeout or get_settings().gemini_timeout_seconds
    errors = []
    for attempt in range(attempts):
        for m in models:
            try:
                return _post(m, body, timeout), m
            except (GeminiError, httpx.HTTPError) as e:
                errors.append(str(e) or type(e).__name__)
        if attempt + 1 < attempts:
            time.sleep(0.6)
    raise GeminiError("; ".join(errors[-4:]))


def _text(resp: dict) -> str:
    try:
        parts = resp["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError):
        raise GeminiError(f"no content (finish: {resp.get('candidates', [{}])[0].get('finishReason', '?')})")
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def _gen_config(**extra) -> dict:
    cfg = dict(extra)
    level = get_settings().gemini_thinking_level
    if level:
        cfg["thinkingConfig"] = {"thinkingLevel": level}
    return cfg


def _json_from(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.S)
        if not m:
            raise GeminiError("model did not return JSON")
        return json.loads(m.group(0))


EXTRACT_GUIDE = """You read what a hirer said (in the country's languages, romanised, or English) and fill a job form.
Rules:
- "task" must be one of trade_codes (pick the closest; null if no trade is mentioned).
- "location_text": the area/landmark name as said (e.g. "G-13", "Saddar"), else null.
- Numbers (headcount, daily_rate, hours_per_day, advance, days, transport_amount, deduction amounts) must be
  numbers the speaker actually said. Never guess. Use null when not said.
- "start_at": ISO-8601 datetime with the timezone offset, computed from "now" and words like aaj/kal/parson/
  subah 8 baje (if a day is said but no hour, use 08:00 local). "payment_day": ISO date (YYYY-MM-DD). Null if no time words.
- deductions: [] only if the speaker clearly said there are none; null if not mentioned.
- advance: 0 only if the speaker said no advance; null if not mentioned.
- transport_mode: "none" | "provided" | "allowance" or null.
Return ONLY a JSON object with exactly the keys of the schema."""


class GeminiLLM:
    name, family, is_mock = "gemini", "gemini", False

    def complete_json(self, *, task: str, system: str, prompt: str, schema: dict) -> dict:
        guide = EXTRACT_GUIDE if task == "extract_job" else ""
        body = {
            "systemInstruction": {"parts": [{"text": f"{system}\n\n{guide}".strip()}]},
            "contents": [{"role": "user", "parts": [{"text": f"JSON schema:\n{json.dumps(schema)}\n\nInput:\n{prompt}"}]}],
            "generationConfig": _gen_config(responseMimeType="application/json", temperature=0),
        }
        resp, _ = generate(_models(get_settings().gemini_text_models), body)
        return _json_from(_text(resp))

    def to_urdu_script(self, text: str) -> str:
        """Safety net: some speech models answer in Hindi (Devanagari) script. Convert to Urdu script."""
        body = {"contents": [{"role": "user", "parts": [{"text":
                "Rewrite this exactly in Urdu (Perso-Arabic) script. Same words, keep digits. Output only the text:\n" + text}]}],
                "generationConfig": _gen_config(temperature=0)}
        resp, _ = generate(_models(get_settings().gemini_text_models), body)
        return _text(resp).strip()


class GeminiASR:
    name, family, is_mock = "gemini", "gemini", False

    def transcribe(self, audio: bytes, mime: str, lang: str) -> Transcript:
        language = LANG_NAMES.get(lang, lang)
        script = "Urdu Nastaliq (Perso-Arabic) script, never Devanagari" if lang == "ur" else f"{language} script"
        body = {
            "systemInstruction": {"parts": [{"text": f"You transcribe short spoken job posts. Write the transcript in {script}. "
                                                      "Keep numbers as digits. Output only the transcript, nothing else."}]},
            "contents": [{"role": "user", "parts": [
                {"inlineData": {"mimeType": (mime or "audio/webm").split(";")[0], "data": base64.b64encode(audio).decode()}},
                {"text": "اس آڈیو کو اردو رسم الخط میں لکھیں۔ صرف متن دیں۔" if lang == "ur" else "Transcribe this audio."}]}],
            "generationConfig": _gen_config(temperature=0),
        }
        resp, model = generate(_models(get_settings().gemini_asr_models), body)
        text = _text(resp).strip()
        if not text:
            raise GeminiError("empty transcript")
        if lang == "ur" and DEVANAGARI.search(text):
            try:
                text = GeminiLLM().to_urdu_script(text)
            except GeminiError as e:
                log.warning("script conversion failed: %s", e)
        return Transcript(text, lang, None, f"gemini:{model}")


def _wav(pcm: bytes, rate: int = 24000) -> bytes:
    hdr = (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " +
           struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm)))
    return hdr + pcm


class GeminiTTS:
    name, family, is_mock = "gemini", "gemini", False

    def synthesize(self, text: str, lang: str) -> Audio:
        s = get_settings()
        body = {"contents": [{"parts": [{"text": text}]}],
                "generationConfig": {"responseModalities": ["AUDIO"],
                                     "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": s.gemini_tts_voice}}}}}
        resp, model = generate(_models(s.gemini_tts_models), body, attempts=1)
        try:
            part = next(p["inlineData"] for p in resp["candidates"][0]["content"]["parts"] if "inlineData" in p)
        except (KeyError, IndexError, StopIteration):
            raise GeminiError("no audio in response")
        data, mime = base64.b64decode(part["data"]), part.get("mimeType", "")
        if "wav" in mime:
            return Audio(data, "audio/wav", f"gemini:{model}")
        m = re.search(r"rate=(\d+)", mime)
        return Audio(_wav(data, int(m.group(1)) if m else 24000), "audio/wav", f"gemini:{model}")


registry.register("llm", "gemini", GeminiLLM)
registry.register("asr", "gemini", GeminiASR)
registry.register("tts", "gemini", GeminiTTS)
