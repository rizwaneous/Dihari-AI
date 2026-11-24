from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

from app import db as database


def test_jeddah_map_to_hirer_contact(client, make_user):
    hirer, _ = make_user("+966500000011", "hirer")
    worker, _ = make_user("+966500000012", "worker")
    other, _ = make_user("+966500000013", "worker")
    start = datetime.now(timezone.utc) + timedelta(days=1)
    fields = dict(task="paint", headcount=1, location_text="Al-Balad, Jeddah",
                  lat=21.4858, lon=39.1875, address_detail="Meet at the side entrance",
                  start_at=start.isoformat(), daily_rate=180, hours_per_day=8,
                  payment_day=start.date().isoformat())
    ids = []
    for shift in (fields, fields | {"task": "labour", "lat": 21.492}):
        posted = client.post("/jobs", json=shift, headers=hirer)
        assert posted.status_code == 201, posted.text
        ids.append(posted.json()["id"])
    assert {j["id"] for j in client.get("/jobs/mine", headers=hirer).json()} == set(ids)
    client.put("/profiles/worker", headers=worker, json={"trades": ["tile"], "radius_km": 5,
               "lat": fields["lat"], "lon": fields["lon"], "area_name": fields["location_text"]}).raise_for_status()
    feed = "/jobs/nearby?lat=21.4858&lon=39.1875&all_trades=true"
    nearby = client.get(feed, headers=worker).json()
    assert [j["id"] for j in nearby] == ids
    assert all(j["currency"] == "SAR" and "address_detail" not in j for j in nearby)
    assert client.get("/jobs/nearby?lat=24.71&lon=46.67&all_trades=true", headers=worker).json() == []
    booking = client.post("/jobs/"+ids[0]+"/book", headers=worker).json()
    agreement = "/agreements/"+booking["agreement_id"]
    assert client.get(agreement, headers=other).status_code == 404
    details = client.get(agreement, headers=worker).json()
    assert details["hirer"]["phone"] == "+966500000011"
    assert details["terms"]["address_detail"] == fields["address_detail"]
    assert details["terms"]["lat"] == fields["lat"]
    assert [j["id"] for j in client.get(feed, headers=other).json()] == ids[1:]


def post(client, make_user, seats):
    hirer, _ = make_user("03000000011", "hirer")
    start = datetime.now(timezone.utc) + timedelta(days=1)
    fields = dict(task="tile", headcount=seats, location_text="G-13", lat=33.6575,
                  lon=72.959, start_at=start.isoformat(), daily_rate=1500,
                  hours_per_day=8, payment_day=start.date().isoformat())
    response = client.post("/jobs", json=fields, headers=hirer)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_booking_retry_partial_fill_and_release(client, make_user):
    job = post(client, make_user, 2)
    w1, _ = make_user("03000000012", "worker")
    w2, _ = make_user("03000000013", "worker")
    endpoint = f"/jobs/{job}/book"
    first = client.post(endpoint, headers=w1).json()
    assert first["status"] == "confirmed"
    assert client.post(endpoint, headers=w1).json() == first
    feed = "/jobs/nearby?lat=33.6575&lon=72.959"
    assert client.get(feed, headers=w2).json()[0]["booked"] == 1
    assert client.post(endpoint, headers=w2).status_code == 200
    assert client.get(feed, headers=w2).json() == []
    assert client.post("/assignments/"+first["assignment_id"]+"/cancel", headers=w1).status_code == 200
    assert client.get(feed, headers=w1).json()[0]["booked"] == 1
    assert client.post(endpoint, headers=w1).status_code == 200


def test_two_workers_claim_last_slot(client, make_user, tmp_path):
    # Independent connections exercise the database lock used by a real server.
    database.init_db("sqlite:///" + (tmp_path / "race.db").as_posix())
    job = post(client, make_user, 1)
    workers = [make_user(phone, "worker")[0] for phone in ("03000000012", "03000000013")]
    ready = Barrier(2)
    def book(headers):
        ready.wait(timeout=10)
        return client.post(f"/jobs/{job}/book", headers=headers).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(book, workers)) == [200, 409]


def test_push_rejects_invalid_registration(client, make_user, monkeypatch):
    from app.settings import get_settings
    worker, _ = make_user("03000000013", "worker")
    for key, value in (("NOTIFY_PROVIDERS", "webpush,log"), ("VAPID_PUBLIC_KEY", "test-public"),
                       ("VAPID_PRIVATE_KEY", "test-private"), ("VAPID_SUBJECT", "mailto:test@example.com")):
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    assert client.get("/notifications/config").json() == {"public_key": "test-public"}
    assert client.post("/notifications/subscribe", headers=worker, json={"endpoint":"invalid"}).status_code == 400


def test_otp_delivery_failure_can_be_retried(client, monkeypatch):
    from app.modules.notifications import get_sms
    monkeypatch.setattr(get_sms(), "send", lambda phone, text: False)
    response = client.post("/auth/request-otp", json={"phone":"03000000013"})
    assert response.status_code == 503
    assert response.json()["detail"] == "sms_unavailable"
