"""PLACEHOLDER for the next AI providers. Copy this file to e.g. `claude.py` / `openai.py` / `azure_speech.py`
(files starting with "_" are not loaded), fill in the calls, add the key to backend/.env, and list the provider
name in ASR_PROVIDERS / TTS_PROVIDERS / LLM_EXTRACT_PROVIDERS / LLM_VERIFY_PROVIDERS.

Good next candidates:
  * LLM verifier (must be a DIFFERENT family from Gemini): Claude (Anthropic API) or GPT (OpenAI API).
  * Urdu TTS with more natural voices: Azure Speech (ur-PK neural voices), ElevenLabs.
  * Urdu ASR: Azure Speech (ur-PK), Google Cloud Speech-to-Text.
  * SMS / WhatsApp OTP: see modules/notifications.register_sms().
Check each provider's current docs and prices before choosing."""
from .. import registry  # noqa: F401
from ..base import Audio, Transcript  # noqa: F401


class ExampleLLM:
    name, family, is_mock = "example", "example-family", False

    def complete_json(self, *, task: str, system: str, prompt: str, schema: dict) -> dict:
        raise NotImplementedError("call your model here and return a dict matching `schema`")


# registry.register("llm", "example", ExampleLLM)
