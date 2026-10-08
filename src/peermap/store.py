"""Where the prices read from Yahoo are kept: a folder locally, a bucket on Cloud Run."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Protocol

from .config import DATA_DIR


class Store(Protocol):
    def get(self, key: str) -> dict | None: ...
    def put(self, key: str, value: dict) -> None: ...


class MemoryStore:
    """For tests."""

    def __init__(self):
        self.items: dict[str, dict] = {}

    def get(self, key: str) -> dict | None:
        value = self.items.get(key)
        return json.loads(json.dumps(value)) if value is not None else None

    def put(self, key: str, value: dict) -> None:
        self.items[key] = json.loads(json.dumps(value))


class FileStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or DATA_DIR / "store")
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> dict | None:
        path = self._path(key)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def put(self, key: str, value: dict) -> None:
        path = self._path(key)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(value, separators=(",", ":")))
            tmp.replace(path)


class GcsStore:
    def __init__(self, bucket: str):
        from google.cloud import storage

        self.bucket = storage.Client().bucket(bucket)

    def get(self, key: str) -> dict | None:
        blob = self.bucket.blob(f"{key}.json")
        if not blob.exists():
            return None
        return json.loads(blob.download_as_bytes())

    def put(self, key: str, value: dict) -> None:
        self.bucket.blob(f"{key}.json").upload_from_string(
            json.dumps(value, separators=(",", ":")), content_type="application/json")


def default_store() -> Store:
    bucket = os.environ.get("PEERMAP_BUCKET", "").strip()
    return GcsStore(bucket) if bucket else FileStore()
