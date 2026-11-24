# Dihari — 3-minute demo script

## Quick prototype demo (one-tap accounts)
1. `cd backend && .venv\Scripts\python scripts/seed.py` (safe to re-run) then `.venv\Scripts\uvicorn app.main:app --reload`.
2. `cd frontend && npm run dev`, open http://localhost:5173.
3. On the welcome screen tap **Try the demo → Hirer**. Tap **Request workers**, pick a trade (the ⚖️ box shows the usual rate and the legal minimum), or tap **Speak** and say the job; Gemini fills the form.
4. Tap the yellow **Switch to Labourer** button in the header. The new job is in the list; open it and tap **Accept**. Repeat with as many jobs as you like.
5. Tap the medal icon in the header to open the **Kaam Card**: level (Naya → Trusted → Expert → Gold Expert), earnings and verified work history.
6. Switch back to the hirer: offers show each worker's level badge.

Demo logins work only while `DEV_MODE=true`.

Setup (once): `cd backend && .venv/bin/python scripts/seed.py && .venv/bin/uvicorn app.main:app` and `cd frontend && npm run dev`. Open two browser windows (hirer / worker). OTP appears on the login screen (`DEV_MODE`, stub SMS). No microphone / ASR yet? Use the **"type instead"** box — the flow is identical (set `MOCK_ASR_FIXED_TEXT` to demo a canned transcript through the server ASR path).

The same story is an automated test: `backend/tests/test_demo_scenario.py`.

## 0:00 — Hirer lowballs and is stopped (window 1: hirer `03001000000`)
1. First-run screen: tap **مزدور چاہئیں**. Log in.
2. Tap the giant mic (or type) and say/type: *"چار مزدور کل صبح 8 بجے جی 13 میں ٹائل کا کام روزانہ 600 روپے"*.
3. The app asks one question at a time: hours → **8**, payment day → **جمعہ**, deductions → **نہیں**, advance → **صفر**, transport → **نہیں**.
4. Red box: **"یہ ریٹ کم از کم دیہاڑی 1000 روپے سے کم ہے"** — the job cannot be posted. A yellow banner says the wage rule is *unverified* (placeholder).

## 0:50 — Hirer fixes the offer
5. Tap **ریٹ 1000 کر دیں** (or step the rate to 1500). The Urdu read-back plays; the second-model verifier line is checked in code.
6. Say **"ہاں"** or tap the green tick. Job posted.

## 1:20 — Worker hears it and accepts (window 2: worker `03002000000`, area G-11)
7. Jobs tab: the new tile job appears as a big card (icon, **Rs 1500**, ~km, start time). Location is fuzzed (~500 m) — exact address is hidden.
8. Tap 🔊: the job is read aloud in Urdu. Tap **قبول**. (Try **اپنا ریٹ**: the stepper cannot go below the offer; the server rejects lower counters too.)

## 1:50 — Hirer picks, work happens
9. Hirer: *My jobs → job → Pick*. Worker's **My work** tab: the agreement is read aloud; tap **میں آؤں گا**. Hirer taps **کام شروع ہو گیا**, then **کام مکمل ہو گیا**. The agreement (immutable, hash-stamped, both sides see it) now shows the exact address and phone numbers.

## 2:15 — A week later: "پیسے نہیں ملے"
10. Time-travel the dev clock: `curl -X POST "localhost:8000/dev/advance-days?days=8" && curl -X POST localhost:8000/dev/tick` (reminders go to both parties).
11. Worker: *My work* → the two giant buttons. Tap red **پیسے نہیں ملے**. The app says it is recorded and a **person** will look at it.

## 2:40 — A human decides
12. Open `http://localhost:8080/admin` (or `:8000/admin`), paste token `demo-reviewer-token` ("Demo Reviewer").
13. The case shows full detail to the reviewer only. Rules proposed follow-ups; click **Approve** on *request_hirer_response*. The hirer receives an Urdu notification **without the worker's name**; the audit log records `reviewer:Demo Reviewer`.
14. Close as *paid* or *unresolved*. The AI decided nothing.
