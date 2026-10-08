"""How the price of each company on the map has moved: today, over a week, a month, since the
start of the year and over a year. The map colours its dots with it.

The figures come from the daily closes of Yahoo Finance (the yfinance library), asked for all the
companies in a few calls, and are counted as the portal counts them: sessions back from the last
close, without dividends. Nothing is scheduled: a visit that finds them old asks for them again
(`Performance.refresh`), at most one refresh at a time. They describe what the price did; they
are not a forecast and say nothing about what it will do.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import PERFORMANCE_TTL_SECONDS, PERIODS, YAHOO_BATCH
from .store import Store

log = logging.getLogger("peermap.performance")

KEY = "performance"
NEW_YORK = ZoneInfo("America/New_York")
# The regular session, with a margin after the bell for the closing prints to arrive.
OPEN, CLOSE = (9, 30), (16, 15)
# A year of sessions and the last close of the year before both fit in this.
HISTORY_DAYS = 400


class PerformanceUnavailable(Exception):
    """Yahoo did not answer for enough companies to call it a refresh."""


def returns(dates: list[str], closes: list[float]) -> list[float | None]:
    """The return over each of PERIODS, from daily closes, oldest first. None where the history
    is too short."""
    out: list[float | None] = []
    for _, back in PERIODS:
        if back is None:  # year to date: against the last close of the year before
            before = [c for d, c in zip(dates, closes) if d[:4] < dates[-1][:4]] if dates else []
            base = before[-1] if before else None
        else:
            base = closes[-1 - back] if len(closes) > back else None
        out.append(round(closes[-1] / base - 1, 4) if base else None)
    return out


def last_close(now: datetime) -> datetime:
    """The most recent moment the regular session ended, weekends skipped. Holidays are not known
    here: on one, the figures are simply read again for nothing."""
    local = now.astimezone(NEW_YORK)
    close = local.replace(hour=CLOSE[0], minute=CLOSE[1], second=0, microsecond=0)
    if local < close:
        close -= timedelta(days=1)
    while close.weekday() >= 5:
        close -= timedelta(days=1)
    return close


def market_open(now: datetime) -> bool:
    local = now.astimezone(NEW_YORK)
    return local.weekday() < 5 and OPEN <= (local.hour, local.minute) < CLOSE


def yahoo_closes(tickers: list[str]) -> dict[str, tuple[list[str], list[float]]]:
    """Daily closes of each ticker over the last year and a bit, from Yahoo. A ticker Yahoo does
    not know is left out."""
    import yfinance as yf

    start = (datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS)).date().isoformat()
    frame = yf.download(tickers, start=start, interval="1d", auto_adjust=False, actions=False,
                        group_by="ticker", threads=True, progress=False)
    out = {}
    for ticker in tickers:
        try:
            closes = frame[ticker]["Close"].dropna()
        except KeyError:
            continue
        if len(closes) >= 2:
            out[ticker] = ([d.strftime("%Y-%m-%d") for d in closes.index], [float(c) for c in closes])
    return out


class Performance:
    """The returns of the companies on the map, kept in the store and refreshed when a visit asks."""

    def __init__(self, store: Store, tickers: list[str],
                 closes: Callable[[list[str]], dict[str, tuple[list[str], list[float]]]] = yahoo_closes,
                 ttl: float = PERFORMANCE_TTL_SECONDS, now: Callable[[], datetime] | None = None,
                 batch: int = YAHOO_BATCH, wait: float = 150.0):
        self.store, self.tickers, self.closes, self.ttl, self.batch = store, tickers, closes, ttl, batch
        self.wait = wait  # how long a visit waits for a refresh another visit started
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()
        self._doc: dict | None = None

    def _read(self) -> dict:
        if self._doc is None:
            self._doc = self.store.get(KEY) or {"as_of": None, "returns": {}}
        return self._doc

    def stale(self, doc: dict | None = None) -> bool:
        doc = doc or self._read()
        if not doc["as_of"]:
            return True
        now, read = self.now(), datetime.fromisoformat(doc["as_of"])
        if market_open(now):
            return (now - read).total_seconds() > self.ttl
        return read < last_close(now)

    def get(self) -> dict:
        doc = self._read()
        return {"as_of": doc["as_of"], "stale": self.stale(doc), "periods": [key for key, _ in PERIODS],
                "returns": doc["returns"]}

    def refresh(self) -> dict:
        """Read the closes again, unless the figures are fresh. One refresh at a time: a second
        visit that asks meanwhile waits for the first one's and gets its figures. A company Yahoo
        does not answer for keeps its last figures."""
        if not self._lock.acquire(timeout=self.wait):
            return self.get()
        try:
            # Another instance may have refreshed since this one last looked.
            self._doc = self.store.get(KEY) or self._read()
            if not self.stale():
                return self.get()
            started, fresh = time.monotonic(), {}
            for i in range(0, len(self.tickers), self.batch):
                chunk = self.tickers[i:i + self.batch]
                try:
                    got = self.closes(chunk)
                except Exception as exc:
                    # The error's name only: its text can carry the address that was asked.
                    log.warning("yahoo closes for %d tickers -> %s", len(chunk), type(exc).__name__)
                    continue
                fresh |= {t: returns(dates, closes) for t, (dates, closes) in got.items()}
            log.info("performance: %d of %d companies in %.1fs", len(fresh), len(self.tickers), time.monotonic() - started)
            if len(fresh) < len(self.tickers) / 2:
                raise PerformanceUnavailable(f"{len(fresh)} of {len(self.tickers)}")
            self._doc = {"as_of": self.now().isoformat(timespec="seconds"), "returns": self._doc["returns"] | fresh}
            self.store.put(KEY, self._doc)
            return self.get()
        finally:
            self._lock.release()
