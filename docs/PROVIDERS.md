# Provider setup

## Map and search

The demo uses Leaflet with attributed OpenStreetMap street tiles. Area names from the country configuration are searched locally first. A submitted landmark search uses Photon when there is no local match. The browser requests the visible map tiles only. Configure VITE_TILE_URL and VITE_GEOCODER_URL at build time to use your own compatible services. Tile and search availability depend on the network.

## SMS and background notifications

Local development defaults to on-screen stub OTPs and database notifications. For SMS delivery, configure SMS_PROVIDER=twilio, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER in the backend environment. For Docker Compose, set DIHARI_ENV_FILE to the runtime environment file path. The sender must be enabled to deliver to the destination. Set DEV_MODE=false and a private SECRET_KEY for a pilot.

For background delivery install the backend with its push extra (`pip install -e ".[push]"`). The backend Docker image includes it. Set NOTIFY_PROVIDERS=webpush,log, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY and VAPID_SUBJECT. Use the URL-safe base64 application public key, the corresponding pywebpush-compatible private key and a mailto contact. Serve the production PWA over HTTPS or localhost. Sign in and select Enable job alerts. The delivery loop reads committed inbox entries and retries transient errors. Nearby-job alerts use the worker’s saved trade, area and radius. Deleting a browser subscription disables background delivery on that device.

## Google Gemini (wired in)

`backend/app/ai/providers/gemini.py` uses one key for job extraction (LLM), Urdu speech-to-text and read-aloud (TTS).
Set in `backend/.env`: `GEMINI_API_KEY`, `ASR_PROVIDERS=gemini,mock`, `TTS_PROVIDERS=gemini,mock`,
`LLM_EXTRACT_PROVIDERS=gemini,mock-a`. Each kind tries a list of models (`GEMINI_TEXT_MODELS`, `GEMINI_ASR_MODELS`,
`GEMINI_TTS_MODELS`) because single models are sometimes overloaded; if all fail, the chain falls back to the offline mock.
Numbers Gemini extracts are still checked against the transcript in code, and the wage floor is still pure code.
The verifier stays `mock-b` until a second, non-Gemini model is added (`providers/_template.py`).

## Voice providers
1. **Check the provider's CURRENT docs first** (languages, pricing, request format). Do not rely on memory. For ASR confirm Urdu, Punjabi, Sindhi and Pashto support and which model/version; for TTS confirm a natural Urdu voice.
2. Create `backend/app/ai/providers/<name>.py`. Implement the interface from `app/ai/base.py`:
   - `ASR.transcribe(audio: bytes, mime: str, lang: str) -> Transcript`
   - `TTS.synthesize(text: str, lang: str) -> Audio`
   - `LLM.complete_json(*, task, system, prompt, schema) -> dict` (must return JSON matching `schema`; set `family`)
   - set `name`, `family`, `is_mock = False`
3. At import time call `registry.register("asr"|"tts"|"llm", "<name>", factory)`. Modules in `providers/` are auto-imported.
4. Put keys in `.env` (names suggested in `.env.example`) and select with `ASR_PROVIDERS=<name>,mock` etc. Chains try providers in order and log provider / latency / failure to the `ai_call_log` table.
5. **Verifier rule:** `LLM_VERIFY_PROVIDERS` must be a *different model family* than `LLM_EXTRACT_PROVIDERS`; the app refuses to start otherwise.
6. Additional messaging adapters: `modules/notifications.register_sms(name, factory)`; web push: `register_push(name, factory)` and set `NOTIFY_PROVIDERS`.
7. Re-run `python -m adversarial.run --llm <name>` for real extraction numbers.

If every provider in a chain fails the API answers `503 {degraded: true}` and the PWA drops to tap-only input / browser `speechSynthesis`.
