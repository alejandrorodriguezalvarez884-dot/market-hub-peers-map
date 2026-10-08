"""Sign-in through Market Hub: the tool admits only requests with a valid hub session cookie."""

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from peermap.api import create_app
from peermap.hubauth import read_user

SECRET = "hub-secret"
HUB = "https://themarkethub.app"
HERE = "https://peers.themarkethub.app"
USER = {"id": "1001", "email": "ana@gmail.com", "name": "Ana", "picture": ""}


def hub_cookie(secret: str = SECRET, user: dict | None = USER) -> str:
    """A session cookie made exactly as the hub makes it (Starlette's SessionMiddleware)."""
    def login(request):
        if user:
            request.session["user"] = user
        return PlainTextResponse("ok")

    hub = Starlette(routes=[Route("/", login)],
                    middleware=[Middleware(SessionMiddleware, secret_key=secret, session_cookie="mh_session")])
    return TestClient(hub).get("/").cookies.get("mh_session", "")


def gated(peers, store):
    return TestClient(create_app(store=store, peers=peers, hub=(HUB, SECRET)), base_url=HERE, follow_redirects=False)


def test_read_user_checks_the_signature_and_age():
    cookie = hub_cookie()
    assert read_user(cookie, SECRET) == USER
    assert read_user(cookie, "another-secret") is None
    assert read_user(cookie[:-2] + "xx", SECRET) is None
    assert read_user(cookie, SECRET, max_age=-1) is None
    assert read_user(None, SECRET) is None
    assert read_user(hub_cookie(user=None), SECRET) is None  # signed in nobody


def test_signed_out_visitors_go_to_the_hub(peers, store):
    c = gated(peers, store)
    assert c.get("/api/health").status_code == 200
    page = c.get("/", params={"t": "AAPL"})
    assert page.status_code == 302
    target = urlparse(page.headers["location"])
    assert f"{target.scheme}://{target.netloc}{target.path}" == f"{HUB}/signin/"
    assert parse_qs(target.query)["next"] == [f"{HERE}/?t=AAPL"]
    api = c.get("/api/peers", headers={"referer": f"{HERE}/?t=KO"})
    assert api.status_code == 401
    # After signing in, back to the page that made the call, not to the API.
    assert parse_qs(urlparse(api.json()["signin"]).query)["next"] == [f"{HERE}/?t=KO"]
    foreign = c.get("/api/peers", headers={"referer": "https://evil.example/x"})
    assert parse_qs(urlparse(foreign.json()["signin"]).query)["next"] == [f"{HERE}/"]
    # Nobody without a session makes the service ask Yahoo.
    assert c.post("/api/performance/refresh").status_code == 401
    c.cookies.set("mh_session", hub_cookie(secret="forged"))
    assert c.get("/api/me").status_code == 401


def test_signed_in_users_get_in(peers, store):
    c = gated(peers, store)
    c.cookies.set("mh_session", hub_cookie())
    assert c.get("/api/me").json() == {"user": USER, "hub": HUB}
    assert c.get("/api/peers/AAPL").status_code == 200


def test_without_hub_settings_the_tool_stays_public(peers, store):
    c = TestClient(create_app(store=store, peers=peers, hub=None))
    assert c.get("/api/me").json() == {"user": None, "hub": None}
    assert c.get("/api/peers").status_code == 200
