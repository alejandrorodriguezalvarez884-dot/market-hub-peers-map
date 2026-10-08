"""The service: the site and the API, from one origin.

    GET  /api/health
    GET  /api/me                    who is signed in to Market Hub, and the hub's address
    GET  /api/peers                 the map: every company, its place and its neighbours
    GET  /api/peers/{ticker}        the companies whose business description is most like this one's
    GET  /api/performance           each company's return today, over a week, a month, YTD and a year
    POST /api/performance/refresh   read the prices again, if the figures are stale

Everything else is the static site, when PEERMAP_STATIC_DIR points at its build.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from .hubauth import HubGate
from .hubauth import settings as hub_settings
from .peers import PeerMap
from .performance import Performance, PerformanceUnavailable
from .store import Store, default_store

log = logging.getLogger("peermap.api")


def create_app(store: Store | None = None, peers: PeerMap | None = None, performance: Performance | None = None,
               static_dir: str | None = None, hub: tuple[str, str] | None | bool = True) -> FastAPI:
    """App factory. Tests pass their own pieces, so they need no network.

    ``hub`` is (hub URL, hub session secret) to admit only people signed in to Market Hub; by
    default it comes from HUB_URL and HUB_SESSION_SECRET, and None leaves the service public."""
    logging.basicConfig(level=logging.INFO)
    # yfinance prints what Yahoo answers for a symbol it does not know; httpx logs every address.
    for noisy in ("httpx", "httpcore", "yfinance"):
        logging.getLogger(noisy).setLevel(logging.CRITICAL if noisy == "yfinance" else logging.WARNING)
    app = FastAPI(title="Peer Map", docs_url=None, redoc_url=None, openapi_url=None)

    origins = [o.strip() for o in os.environ.get("PEERMAP_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"])
    hub = hub_settings() if hub is True else hub or None
    if hub:
        app.add_middleware(HubGate, hub_url=hub[0], secret=hub[1])

    peer_map = peers or PeerMap.load()
    # The map only changes with a deploy: it is written out once and the browser may keep it.
    overview = json.dumps(peer_map.overview(), separators=(",", ":")).encode()
    performance = performance or Performance(store or default_store(), [c["ticker"] for c in peer_map.companies])

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/me")
    def me(request: Request) -> dict:
        return {"user": getattr(request.state, "user", None), "hub": hub[0] if hub else None}

    @app.get("/api/peers")
    def peers_view() -> Response:
        return Response(overview, media_type="application/json", headers={"Cache-Control": "private, max-age=3600"})

    @app.get("/api/peers/{ticker}")
    def peers_of(ticker: str) -> dict:
        found = peer_map.get(ticker)
        if not found:
            raise HTTPException(404, "This company is not on the map.")
        return found

    @app.get("/api/performance")
    def performance_view() -> dict:
        return performance.get()

    @app.post("/api/performance/refresh")
    def performance_refresh() -> dict:
        """What the page asks for when it finds the figures stale. It only goes to Yahoo then, and
        never while another refresh runs."""
        try:
            return performance.refresh()
        except PerformanceUnavailable:
            log.warning("performance refresh failed: too few companies answered")
            raise HTTPException(503, "Prices are not available right now. The map works without them.") from None

    static_dir = static_dir or os.environ.get("PEERMAP_STATIC_DIR", "")
    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="site")
    return app
