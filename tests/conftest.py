"""A small map and a store in memory, so no test needs the network."""

from __future__ import annotations

import pytest

from peermap.peers import PeerMap
from peermap.store import MemoryStore

MAP = {"built": "2026-10-08", "model": "m", "k": 1, "labels": [{"text": "Software", "x": 0.5, "y": 0.5}], "companies": [
    {"ticker": "AAPL", "tickers": ["AAPL"], "name": "Apple Inc.", "industry": "Electronic Computers", "form": "10-K",
     "filed": "2025-10-31", "url": "https://www.sec.gov/a", "x": 0.1, "y": 0.2, "peers": [[1, 0.61]]},
    {"ticker": "GOOGL", "tickers": ["GOOGL", "GOOG"], "name": "Alphabet Inc.", "industry": "Computer Programming", "form": "10-K",
     "filed": "2026-02-05", "url": "https://www.sec.gov/g", "x": 0.3, "y": 0.4, "peers": [[0, 0.61]]}]}


@pytest.fixture
def peers():
    return PeerMap(MAP)


@pytest.fixture
def store():
    return MemoryStore()
