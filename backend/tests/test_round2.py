"""Round 2: free today + invites, urgent posts, attendance, hisaab, late cancellation, teams, safety, skills,
shareable Kaam Card, voice commands."""
from datetime import datetime, timedelta, timezone

from app.db import CLOCK


def body(**kw):
    start = datetime.now(timezone.utc) + timedelta(days=1)
    b = dict(task="tile", headcount=2, location_text="G-13", lat=33.6575, lon=72.959, start_at=start.isoformat(),
             daily_rate=1500, hours_per_day=8, payment_day=(start + timedelta(days=2)).date().isoformat())
    b.update(kw)
    return b


def setup(client, make_user, n=1, **kw):
    hirer, _ = make_user("+923005550000", "hirer")
    workers = []
    for i in range(n):
        h, uid = make_user(f"+92300555{i + 1:04d}", "worker")
        client.put("/profiles/worker", headers=h, json={"trades": ["tile", "labour"], "lat": 33.6575, "lon": 72.959,
                                                       "area_name": "G-13", "radius_km": 10}).raise_for_status()
        workers.append((h, uid))
    jid = client.post("/jobs", headers=hirer, json=body(**kw)).json()["id"]
    return hirer, workers, jid


def test_free_today_and_direct_invite(client, make_user):
    hirer, [(w, wid)], jid = setup(client, make_user)
    assert client.get("/workers/available?lat=33.6575&lon=72.959", headers=hirer).json() == []
    r = client.post("/me/available", headers=w, json={"available": True}).json()
    assert r["available"] and client.get("/profiles/me", headers=w).json()["available_today"]
    free = client.get("/workers/available?lat=33.6575&lon=72.959&trade=tile", headers=hirer).json()
    assert [x["worker_id"] for x in free] == [wid] and free[0]["tier"]["code"] == "naya" and "phone" not in free[0]
    assert client.post(f"/jobs/{jid}/invite", headers=hirer, json={"worker_id": wid}).status_code == 201
    inv = client.get("/my/invites", headers=w).json()
    assert inv[0]["job"]["id"] == jid and inv[0]["job"]["invited"]
    client.post(f"/jobs/{jid}/book", headers=w).raise_for_status()
    assert client.get("/my/invites", headers=w).json() == []
    client.post("/me/available", headers=w, json={"available": False})
    assert client.get("/workers/available?lat=33.6575&lon=72.959", headers=hirer).json() == []


def test_urgent_post_pings_free_workers_and_sorts_first(client, make_user):
    hirer, [(w, wid)], normal = setup(client, make_user)
    client.post("/me/available", headers=w, json={"available": True})
    urgent = client.post("/jobs", headers=hirer, json=body(task="labour", urgent=True, start_at=(datetime.now(timezone.utc) + timedelta(hours=3)).isoformat())).json()
    assert urgent["urgent"]
    feed = client.get("/jobs/nearby?all_trades=true", headers=w).json()
    assert feed[0]["id"] == urgent["id"]
    titles = [n["title"] for n in client.get("/notifications", headers=w).json()]
    assert any("ابھی" in t or "now" in t for t in titles)
    assert client.get("/jobs/fair-rate?task=tile", headers=hirer).json()["urgent_suggested"] >= 1500


def test_check_in_out_and_hisaab(client, make_user):
    hirer, [(w, wid)], jid = setup(client, make_user, days=2)
    asg = client.post(f"/jobs/{jid}/book", headers=w).json()["assignment_id"]
    assert client.post(f"/assignments/{asg}/check-in", headers=w, json={}).status_code == 409   # not a work day yet
    CLOCK.offset = timedelta(days=1, hours=1)
    r = client.post(f"/assignments/{asg}/check-in", headers=w, json={"lat": 33.66, "lon": 72.959}).json()
    assert r["distance_m"] < 500 and not r["far"]
    assert client.post(f"/assignments/{asg}/check-out", headers=w).status_code == 200
    assert len(client.get(f"/assignments/{asg}/attendance", headers=hirer).json()) == 1
    # hirer gives an advance by JazzCash with a transaction id; worker confirms; worker records kharchi received
    h = client.post(f"/assignments/{asg}/hisaab", headers=hirer, json={"kind": "advance", "amount": 500, "method": "jazzcash", "reference": "TX123"}).json()
    assert h["earned"] == 1500 and h["received"] == 0 and h["pending_confirmation"] == 500
    entry = h["entries"][0]
    assert entry["proof"] and not entry["confirmed"]
    assert client.post(f"/hisaab/{entry['id']}/confirm", headers=hirer).status_code == 403   # only the worker confirms
    h = client.post(f"/hisaab/{entry['id']}/confirm", headers=w).json()
    assert h["received"] == 500 and h["balance"] == 1000
    h = client.post(f"/assignments/{asg}/hisaab", headers=w, json={"kind": "kharchi", "amount": 200}).json()
    assert h["balance"] == 800 and "800" in h["speak"]
    assert client.post(f"/assignments/{asg}/hisaab", headers=w, json={"kind": "deduction", "amount": 100}).status_code == 403
    CLOCK.offset = timedelta(0)


def test_late_cancellation_fee(client, make_user):
    hirer, [(w, wid)], jid = setup(client, make_user, start_at=(datetime.now(timezone.utc) + timedelta(hours=5)).isoformat())
    asg = client.post(f"/jobs/{jid}/book", headers=w).json()["assignment_id"]
    r = client.post(f"/jobs/{jid}/cancel", headers=hirer).json()
    assert r["late_fee_workers"] == 1
    assert client.get(f"/assignments/{asg}/hisaab", headers=w).json()["cancellation_fees"] == 300
    me = client.get("/profiles/me", headers=hirer).json()["id"]
    assert client.get(f"/reputation/{me}", headers=w).json()["late_cancellations"] == 1


def test_early_cancellation_is_free(client, make_user):
    hirer, [(w, wid)], jid = setup(client, make_user)   # starts in 24 h
    asg = client.post(f"/jobs/{jid}/book", headers=w).json()["assignment_id"]
    assert client.post(f"/jobs/{jid}/cancel", headers=hirer).json()["late_fee_workers"] == 0


def test_team_roster_booking_and_payroll(client, make_user):
    hirer, [(w1, id1)], jid = setup(client, make_user, headcount=3)
    team = client.post("/teams", headers=hirer, json={"name": "Kamran crew"}).json()
    client.post(f"/teams/{team['id']}/members", headers=hirer, json={"phone": "+923005550001"}).raise_for_status()
    t = client.post(f"/teams/{team['id']}/members", headers=hirer, json={"phone": "03119998877", "name": "Bashir"}).json()
    assert len(t["members"]) == 2 and any(m["name"] == "Bashir" and not m["has_app"] for m in t["members"])
    ids = [m["worker_id"] for m in t["members"]]
    booked = client.post(f"/jobs/{jid}/book-team", headers=hirer, json={"worker_ids": ids}).json()
    assert len(booked) == 2
    CLOCK.offset = timedelta(days=1, hours=1)
    for b in booked:   # thekedar marks attendance for his crew
        client.post(f"/assignments/{b['assignment_id']}/check-in", headers=hirer, json={}).raise_for_status()
    p = client.get(f"/teams/{team['id']}/payroll?days=7", headers=hirer).json()
    assert p["total_balance"] == 3000 and all(r["days"] == 1 for r in p["rows"])
    csv = client.get(f"/teams/{team['id']}/payroll?format=csv", headers=hirer)
    assert csv.headers["content-type"].startswith("text/csv") and "Bashir" in csv.text
    other, _ = make_user("+923005559999", "hirer")
    assert client.get(f"/teams/{team['id']}/payroll", headers=other).status_code == 404
    CLOCK.offset = timedelta(0)


def test_sos_notifies_contact_and_hirer(client, make_user):
    from app.modules.notifications import get_sms
    hirer, [(w, wid)], jid = setup(client, make_user)
    client.post(f"/jobs/{jid}/book", headers=w)
    client.put("/me/safety-contact", headers=w, json={"name": "Bhai", "phone": "03001112233"}).raise_for_status()
    r = client.post("/safety/sos", headers=w, json={"lat": 33.6, "lon": 72.9}).json()
    assert set(r["notified"]) == {"contact", "hirer"} and r["emergency_number"] == "1122"
    assert any(p == "+923001112233" and "SOS" in t for p, t in get_sms().outbox)


def test_endorse_skill_needs_completed_job_and_shows_on_card(client, make_user):
    hirer, [(w, wid)], jid = setup(client, make_user, headcount=1)
    assert client.post(f"/workers/{wid}/endorse", headers=hirer, json={"trade": "tile", "years": 3}).status_code == 409
    asg = client.post(f"/jobs/{jid}/book", headers=w).json()["assignment_id"]
    CLOCK.offset = timedelta(days=1, hours=1)
    client.post(f"/jobs/{jid}/start", headers=hirer).raise_for_status()
    client.post(f"/jobs/{jid}/complete", headers=hirer, json={}).raise_for_status()
    CLOCK.offset = timedelta(0)
    r = client.post(f"/workers/{wid}/endorse", headers=hirer, json={"trade": "tile", "years": 3}).json()
    assert r["skills"] == [{"trade": "tile", "endorsements": 1, "years": 3}]
    link = client.get("/my/card-link", headers=w).json()
    card = client.get(f"/public/card/{link['token']}").json()
    assert card["skills"][0]["trade"] == "tile" and len(card["history"]) == 1 and "location_text" not in card["history"][0]
    assert client.get(f"/public/card/{wid}-000000000000").status_code == 404


def test_voice_commands(client, make_user):
    hirer, [(w, wid)], jid = setup(client, make_user)
    say = lambda h, t: client.post("/voice/command", headers=h, json={"transcript": t}).json()  # noqa: E731
    assert say(w, "مجھے آج کام چاہیے")["action"] == "find_jobs"
    assert say(w, "main aaj farigh hoon")["action"] == "set_available"
    assert say(w, "میرا حساب بتاؤ")["action"] == "hisaab"
    assert say(w, "pohanch gaya hoon")["action"] == "check_in"
    assert say(w, "bachao")["action"] == "sos"
    assert say(hirer, "2 mistri chahiye kal G-13 mein")["action"] == "post_job"
    assert say(hirer, "kaun farigh hai")["action"] == "free_workers"
    r = say(w, "blah")
    assert r["action"] == "unknown" and r["say"]


def test_new_column_added_to_existing_database(tmp_path):
    """Old local databases (created before jobs.urgent existed) are upgraded in place."""
    import sqlite3
    from app import db as dbmod
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE jobs (id VARCHAR(32) PRIMARY KEY, task VARCHAR(40))")
    con.execute("INSERT INTO jobs VALUES ('a', 'tile')")
    con.commit(); con.close()
    dbmod.init_db(f"sqlite:///{path}")
    cols = [r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(jobs)")]
    assert "urgent" in cols and "flagged" in cols
    dbmod.init_db("sqlite://")
