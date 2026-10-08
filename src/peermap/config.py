"""Constants of the service. Nothing here costs money: the map is built with an open model on the
owner's machine and prices come from Yahoo Finance, which takes no key."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.environ.get("PEERMAP_DATA_DIR", ROOT / "data"))

# --- SEC EDGAR: the annual reports the map is built from ------------------------------------

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_SUBMISSIONS_PAGE_URL = "https://data.sec.gov/submissions/{name}"
SEC_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
# The SEC asks for at most 10 requests per second and a contact in the User-Agent.
SEC_RPS = 8.0

# --- The map --------------------------------------------------------------------------------

# The map is built by hand on the owner's machine (`make peers`) and shipped with the code: the
# service only reads this file.
PEERS_FILE = Path(os.environ.get("PEERS_FILE", Path(__file__).resolve().parent / "peers.json"))
# How many companies are read, from the top of the SEC list (ordered roughly by size). About
# seven in eight have a Business section to read, so some 1,500 end up on the map.
PEERS_UNIVERSE = 1725
# Neighbours kept for each company.
PEERS_K = 10
# An open embedding model that runs on a CPU, through fastembed (ONNX). No key, no paid API.
PEERS_MODEL = os.environ.get("PEERS_MODEL", "BAAI/bge-small-en-v1.5")

# --- Performance: how each company's price has moved ----------------------------------------

# The spans the dots can be coloured by, as the portal counts them: sessions back from the last
# close (None: from the last close of the year before).
PERIODS = (("1d", 1), ("1w", 5), ("1m", 21), ("ytd", None), ("1y", 252))
# Nothing is scheduled: a visit that finds the figures older than this, with the market open, asks
# Yahoo again. With the market closed they are read once more after the close and then kept.
PERFORMANCE_TTL_SECONDS = 15 * 60
# Tickers asked from Yahoo in one call.
YAHOO_BATCH = 200
