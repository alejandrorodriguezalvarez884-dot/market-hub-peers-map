"""The peer map as the service reads it: which companies describe a business like this one's.

The file is built by hand with `make peers` (see build.py) from the Business section of each
company's latest annual report, and shipped with the code. Here it is only looked up: nothing is
downloaded and no model runs. Similar means the texts are alike; it says nothing about which
company is better, and it is not a list of things to buy.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import PEERS_FILE


class PeerMap:
    def __init__(self, data: dict | None = None):
        self.data = data or {"built": None, "model": None, "k": 0, "labels": [], "companies": []}
        self.companies: list[dict] = self.data["companies"]
        # Every share class leads to its company: GOOG and GOOGL are one point on the map.
        self._index = {t: i for i, c in enumerate(self.companies) for t in c["tickers"]}

    @classmethod
    def load(cls, path: Path | None = None) -> PeerMap:
        """The map on disk, or an empty one when it has not been built yet."""
        path = path or PEERS_FILE
        return cls(json.loads(path.read_text(encoding="utf-8")) if path.exists() else None)

    def get(self, ticker: str) -> dict | None:
        """A company with its neighbours, nearest first, or ``None`` when it is not on the map."""
        i = self._index.get(ticker.strip().upper().replace(".", "-"))
        if i is None:
            return None
        c = self.companies[i]
        peers = [{**self._brief(self.companies[j]), "similarity": s} for j, s in c["peers"]]
        return {**self._brief(c), "form": c["form"], "filed": c["filed"], "url": c["url"], "peers": peers}

    def overview(self) -> dict:
        """Everything the map page draws, in one answer: points, neighbours and place names."""
        return {
            "built": self.data["built"],
            "labels": self.data["labels"],
            "companies": [{**self._brief(c), "x": c["x"], "y": c["y"], "form": c["form"], "filed": c["filed"],
                           "url": c["url"], "peers": c["peers"]} for c in self.companies],
        }

    @staticmethod
    def _brief(c: dict) -> dict:
        return {"ticker": c["ticker"], "name": c["name"], "industry": c["industry"]}
