"""The API, with the small map of conftest and prices that never leave the test."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from peermap.api import create_app
from peermap.peers import PeerMap
from peermap.performance import Performance

NOW = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)


def client(peers, store, closes=None) -> TestClient:
    closes = closes or (lambda tickers: {t: (["2026-10-06", "2026-10-07"], [100.0, 102.0]) for t in tickers})
    performance = Performance(store, [c["ticker"] for c in peers.companies], closes=closes, now=lambda: NOW)
    return TestClient(create_app(store=store, peers=peers, performance=performance, hub=None))


def test_the_map_and_a_company_s_neighbours(peers, store):
    c = client(peers, store)
    assert c.get("/api/health").json() == {"ok": True}
    found = c.get("/api/peers/aapl").json()
    assert found["peers"] == [{"ticker": "GOOGL", "name": "Alphabet Inc.", "industry": "Computer Programming", "similarity": 0.61}]
    assert found["url"] == "https://www.sec.gov/a" and found["filed"] == "2025-10-31"
    assert c.get("/api/peers/goog").json()["ticker"] == "GOOGL"  # any share class finds the company
    missing = c.get("/api/peers/INTC")
    assert missing.status_code == 404 and "not on the map" in missing.json()["detail"]
    overview = c.get("/api/peers").json()
    assert [p["ticker"] for p in overview["companies"]] == ["AAPL", "GOOGL"]
    assert overview["companies"][0]["peers"] == [[1, 0.61]] and overview["labels"][0]["text"] == "Software"


def test_opening_the_page_never_asks_yahoo_and_the_refresh_does(peers, store):
    asked = []

    def closes(tickers):
        asked.append(tickers)
        return {t: (["2026-10-06", "2026-10-07"], [100.0, 102.0]) for t in tickers}

    c = client(peers, store, closes)
    before = c.get("/api/performance").json()
    assert before["stale"] is True and before["returns"] == {} and not asked
    after = c.post("/api/performance/refresh").json()
    assert after["stale"] is False and after["returns"]["AAPL"] == [0.02, None, None, None, None]
    assert c.get("/api/performance").json() == after
    c.post("/api/performance/refresh")
    assert len(asked) == 1


def test_without_prices_the_map_still_works(peers, store):
    def broken(tickers):
        raise RuntimeError("no answer")

    c = client(peers, store, broken)
    failed = c.post("/api/performance/refresh")
    assert failed.status_code == 503 and "not available" in failed.json()["detail"]
    assert c.get("/api/peers").status_code == 200


def test_without_a_built_map_the_service_still_starts(store):
    c = client(PeerMap(), store)
    assert c.get("/api/peers").json()["companies"] == []
    assert c.get("/api/peers/AAPL").status_code == 404
