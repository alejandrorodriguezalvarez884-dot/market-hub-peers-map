"""The batch behind the peer map. Run by hand on the owner's machine (`make peers`), never by the service.

It reads how each company describes its own business in its latest annual report (SEC EDGAR),
turns that text into a vector with an open embedding model that runs on this machine, and keeps
each company's nearest neighbours and a place on a 2D map. Three steps, each of which picks up
where it stopped:

    fetch    the Business section of each company's latest 10-K (or 20-F)  -> data/peers/text/
    embed    one vector per company                                        -> data/peers/vectors.npz
    build    neighbours, map and place names                               -> src/peermap/peers.json

Nothing here calls a paid API. numpy, fastembed and scikit-learn are only needed by `embed` and
`build` (`uv sync --group build`) and are imported there, so the service does not carry them.
"""

from __future__ import annotations

import html
import json
import re
from collections import Counter
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .config import (DATA_DIR, PEERS_FILE, PEERS_K, PEERS_MODEL, PEERS_UNIVERSE, SEC_ARCHIVE_URL,
                     SEC_SUBMISSIONS_PAGE_URL, SEC_SUBMISSIONS_URL, SEC_TICKERS_URL)
from .sec import sec_get, sec_get_text

WORK_DIR = DATA_DIR / "peers"

# --- Which companies ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Listed:
    cik: int
    ticker: str  # the first one the SEC lists for the company
    tickers: tuple[str, ...]  # every share class (GOOGL and GOOG are one company)
    name: str


def universe(rows: Iterable[dict], size: int = PEERS_UNIVERSE) -> list[Listed]:
    """The first ``size`` companies of the SEC list, which is ordered roughly by market value.

    One entry per company, not per ticker: share classes of the same company share its CIK."""
    by_cik: dict[int, list[dict]] = {}
    for row in rows:
        by_cik.setdefault(int(row["cik_str"]), []).append(row)
    out = []
    for cik, group in by_cik.items():
        tickers = tuple(dict.fromkeys(str(r["ticker"]).upper() for r in group))
        out.append(Listed(cik, tickers[0], tickers, str(group[0]["title"])))
        if len(out) >= size:
            break
    return out


# --- Which filing -------------------------------------------------------------------------------

# The annual report of a US company and of a foreign one. Amendments (10-K/A) are left out: they
# usually carry only the part that was missing.
ANNUAL_FORMS = ("10-K", "20-F")


def latest_annual(filings: dict) -> dict | None:
    """The newest annual report in one page of a company's filing index (newest first)."""
    forms = filings.get("form", [])
    for i, form in enumerate(forms):
        if form in ANNUAL_FORMS and filings["primaryDocument"][i]:
            return {"form": form, "accession": filings["accessionNumber"][i],
                    "document": filings["primaryDocument"][i], "filed": filings["filingDate"][i],
                    "period": filings["reportDate"][i]}
    return None


def find_annual(submissions: dict, get: Callable[[str], dict] = sec_get, max_pages: int = 12) -> dict | None:
    """The newest annual report of a company. The index's first page holds about a thousand
    filings, which for a bank that files prospectuses every day is less than a year: then the
    older pages are read too, up to ``max_pages``."""
    filings = submissions.get("filings", {})
    found = latest_annual(filings.get("recent", {}))
    if found:
        return found
    for page in filings.get("files", [])[:max_pages]:
        found = latest_annual(get(SEC_SUBMISSIONS_PAGE_URL.format(name=page["name"])))
        if found:
            return found
    return None


# --- From a filing to the text of its Business section ------------------------------------------

_DROP = re.compile(r"<(ix:header|script|style|head)\b.*?</\1\s*>", re.S | re.I)
_BREAK = re.compile(r"<(?:br\s*/?|/?(?:p|div|tr|li|h[1-6]|table|ul|ol))\b[^>]*>", re.I)
_CELL = re.compile(r"</t[dh]\s*>", re.I)
_TAG = re.compile(r"<[^>]*>")
_SPACE = re.compile(r"[ \t  -​ 　]+")
# What a page leaves behind once its markup is gone: its number and the link back to the index.
_FURNITURE = re.compile(r"^(?:\d{1,3}|table of contents|index to financial statements)$", re.I)
_BARE_ITEM = re.compile(r"^(?:part\s+[iv]+\W+)?items?\s*\d+[a-c]?\s*(?:(?:and|&)\s*\d+[a-c]?\s*)?[.:]?$", re.I)


def to_lines(markup: str) -> list[str]:
    """The readable lines of a filing's HTML, one per paragraph or table row."""
    text = _DROP.sub(" ", markup)
    text = _BREAK.sub("\n", text)
    text = _CELL.sub(" ", text)
    text = html.unescape(_TAG.sub("", text))
    lines = []
    for raw in text.split("\n"):
        line = _SPACE.sub(" ", raw).strip()
        if not line or _FURNITURE.match(line):
            continue
        # "Item 1." and "Business" often sit in two cells or two paragraphs: read them as one line.
        if lines and _BARE_ITEM.match(lines[-1]):
            lines[-1] = f"{lines[-1]} {line}"
        else:
            lines.append(line)
    return lines


_DASH = r"[.:|–—-]?"
_PART = r"(?:part\s+i\b\W*)?"
_ITEM_1 = rf"^{_PART}items?\s*1\b\s*\.?\s*(?:(?:and|&)\s*2\s*\.?\s*)?{_DASH}\s*"
_AFTER_ITEM_1 = re.compile(rf"^{_PART}item\s*(?:1\s*[ab]|2|3)\b", re.I)
# form -> pairs of (the heading that opens the section, the headings that close it), tried in
# order: the first pair that finds a section wins.
_SECTION = {
    "10-K": (
        (re.compile(rf"{_ITEM_1}(?:\w+\s+){{0,3}}business", re.I), _AFTER_ITEM_1),
        # Item 1 under another title ("Item 1. General"): in a 10-K it is the business all the same.
        (re.compile(rf"{_ITEM_1}\w", re.I), _AFTER_ITEM_1),
        # A few reports head their sections without the item number (Morgan Stanley's, McDonald's).
        (re.compile(r"^business(?: summary| overview)?$", re.I), re.compile(r"^risk factors$", re.I)),
    ),
    "20-F": (
        # "Information on the Company", on one line or two, or on the company by its name.
        (re.compile(rf"^{_PART}item\s*4\b\s*\.?\s*{_DASH}\s*information\b", re.I),
         re.compile(rf"^{_PART}item\s*(?:4\s*a|5)\b", re.I)),
    ),
}
HEADING_MAX = 100  # a longer line that starts with "Item 1A" is a sentence, not a heading
SECTION_MIN = 3000  # shorter than this, it is the table of contents or "see the annual report"
SECTION_MAX = 150_000


def business_section(lines: list[str], form: str = "10-K") -> str | None:
    """The text between the heading of the Business section and the next item's heading.

    The same headings appear in the table of contents, a few lines apart: of every stretch that
    runs from an opening heading to the next closing one, the longest is the section. ``None``
    when there is none worth the name, as in reports that only point, item by item, to the pages
    of an annual report laid out their own way (Intel's, GE's, ASML's)."""
    for start_re, end_re in _SECTION[form]:
        best: tuple[int, int, int] | None = None
        for i, line in enumerate(lines):
            if len(line) > HEADING_MAX or not start_re.match(line):
                continue
            end = next((j for j in range(i + 1, len(lines))
                        if len(lines[j]) <= HEADING_MAX and end_re.match(lines[j])), None)
            if end is None:
                continue
            size = sum(len(l) for l in lines[i + 1:end])
            if best is None or size > best[0]:
                best = (size, i + 1, end)
        if best and best[0] >= SECTION_MIN:
            return "\n".join(lines[best[1]:best[2]])[:SECTION_MAX]
    return None


# --- Step 1: fetch ------------------------------------------------------------------------------


def read_company(company: Listed, get: Callable[[str], dict] = sec_get,
                 get_text: Callable[[str], str] = sec_get_text) -> dict:
    """One company's record: who it is, which filing was read and the section's text, or why not."""
    submissions = get(SEC_SUBMISSIONS_URL.format(cik=company.cik))
    record = {"cik": company.cik, "ticker": company.ticker, "tickers": list(company.tickers),
              "name": submissions.get("name") or company.name, "sic": submissions.get("sic") or "",
              "industry": submissions.get("sicDescription") or ""}
    filing = find_annual(submissions, get)
    if not filing:
        return {**record, "skipped": "no 10-K or 20-F on file"}
    url = SEC_ARCHIVE_URL.format(cik=company.cik, accession=filing["accession"].replace("-", ""),
                                 document=filing["document"])
    record |= {**filing, "url": url}
    text = business_section(to_lines(get_text(url)), filing["form"])
    if not text:
        return {**record, "skipped": "no Business section found in the filing"}
    return {**record, "text": text}


def _text_path(cik: int) -> Path:
    return WORK_DIR / "text" / f"{cik}.json"


def load_records() -> list[dict]:
    """Every record fetched so far, in the order of the SEC list."""
    order = WORK_DIR / "universe.json"
    if not order.exists():
        return []
    out = []
    for cik in json.loads(order.read_text()):
        path = _text_path(cik)
        if path.exists():
            out.append(json.loads(path.read_text(encoding="utf-8")))
    return out


def fetch(size: int = PEERS_UNIVERSE, workers: int = 4, retry: bool = False,
          say: Callable[[str], None] = print) -> dict:
    """Read the companies that have not been read yet. ``retry`` also re-reads the skipped ones."""
    rows = sec_get(SEC_TICKERS_URL)
    companies = universe(rows.values() if isinstance(rows, dict) else rows, size)
    (WORK_DIR / "text").mkdir(parents=True, exist_ok=True)
    (WORK_DIR / "universe.json").write_text(json.dumps([c.cik for c in companies]))

    def pending(c: Listed) -> bool:
        path = _text_path(c.cik)
        if not path.exists():
            return True
        return retry and "skipped" in json.loads(path.read_text(encoding="utf-8"))

    todo = [c for c in companies if pending(c)]
    say(f"{len(companies)} companies, {len(todo)} to read")

    def one(c: Listed) -> dict:
        try:
            record = read_company(c)
        except Exception as exc:  # one company that fails must not stop the other 1,499
            return {"cik": c.cik, "ticker": c.ticker, "failed": type(exc).__name__}
        _text_path(c.cik).write_text(json.dumps(record), encoding="utf-8")
        return record

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for record in pool.map(one, todo):
            done += 1
            what = record.get("failed") or record.get("skipped") or f"{len(record['text']):,} chars"
            say(f"[{done}/{len(todo)}] {record['ticker']:7} {what}")
    return summary()


def summary() -> dict:
    records = load_records()
    reasons = Counter(r["skipped"] for r in records if "skipped" in r)
    return {"read": len(records), "with_text": sum("text" in r for r in records), "skipped": dict(reasons)}


# --- Step 2: embed ------------------------------------------------------------------------------

CHUNK_CHARS = 1600  # about 400 tokens: under the 512 the model reads, so nothing is cut off


def chunks(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """The text in pieces of at most ``size`` characters, cut between paragraphs when it can."""
    out, current = [], ""
    for paragraph in text.split("\n"):
        while len(paragraph) > size:  # a paragraph longer than a piece: cut at a sentence end
            cut = paragraph.rfind(". ", 0, size) + 1 or size
            if current:
                out.append(current)
                current = ""
            out.append(paragraph[:cut].strip())
            paragraph = paragraph[cut:].strip()
        if current and len(current) + 1 + len(paragraph) > size:
            out.append(current)
            current = paragraph
        else:
            current = f"{current}\n{paragraph}" if current else paragraph
    if current:
        out.append(current)
    return out


def _vectors_path() -> Path:
    return WORK_DIR / "vectors.npz"


def embed(model: str = PEERS_MODEL, say: Callable[[str], None] = print, encode=None) -> int:
    """One vector per company: the mean of the vectors of its section's pieces.

    Vectors already computed with the same model for the same filing are kept. ``encode`` takes a
    list of texts and returns their vectors; by default it is the fastembed model."""
    import numpy as np

    records = [r for r in load_records() if "text" in r]
    kept: dict[tuple[int, str], object] = {}
    path = _vectors_path()
    if path.exists():
        old = np.load(path, allow_pickle=False)
        if str(old["model"]) == model:
            kept = {(int(c), str(a)): v for c, a, v in zip(old["cik"], old["accession"], old["vector"])}
    todo = [r for r in records if (r["cik"], r["accession"]) not in kept]
    say(f"{len(records)} companies with text, {len(todo)} to embed with {model}")
    if todo and encode is None:
        from fastembed import TextEmbedding

        # The model's files (about 70 MB) are downloaded once, next to the rest of the batch's work.
        loaded = TextEmbedding(model_name=model, cache_dir=str(WORK_DIR / "model"))
        # Small batches: measured faster on a CPU than big ones, which pad every text to the longest.
        encode = lambda texts: np.array(list(loaded.embed(texts, batch_size=4)))  # noqa: E731

    def save() -> None:
        rows = [r for r in records if (r["cik"], r["accession"]) in kept]
        np.savez(path, model=model, cik=np.array([r["cik"] for r in rows], dtype=np.int64),
                 accession=np.array([r["accession"] for r in rows]),
                 vector=np.array([kept[(r["cik"], r["accession"])] for r in rows], dtype=np.float32))

    for n, record in enumerate(todo, start=1):
        pieces = chunks(record["text"])
        kept[(record["cik"], record["accession"])] = np.asarray(encode(pieces)).mean(axis=0)
        if n % 25 == 0 or n == len(todo):
            save()
            say(f"[{n}/{len(todo)}] {record['ticker']:7} {len(pieces)} pieces")
    if not todo:
        save()
    return len(todo)


# --- Step 3: build ------------------------------------------------------------------------------


def unit(vectors):
    """Vectors with what every annual report has in common taken out, at length one.

    Every Business section talks about employees, regulation and competition, so raw vectors all
    point the same way and every company looks like every other. Subtracting the mean leaves what
    sets each one apart."""
    import numpy as np

    centred = vectors - vectors.mean(axis=0)
    return centred / np.linalg.norm(centred, axis=1, keepdims=True)


def neighbours(vectors, k: int = PEERS_K):
    """For each row, the ``k`` other rows with the highest cosine similarity, nearest first."""
    import numpy as np

    sim = vectors @ vectors.T
    np.fill_diagonal(sim, -np.inf)
    k = min(k, len(vectors) - 1)
    order = np.argsort(-sim, axis=1)[:, :k]
    return order, np.take_along_axis(sim, order, axis=1)


def layout(vectors):
    """A place on a plane for each company, close to the companies it is like. Between 0 and 1."""
    from sklearn.manifold import TSNE

    n = len(vectors)
    xy = TSNE(n_components=2, metric="cosine", init="pca", perplexity=min(30.0, max(2.0, (n - 1) / 3)),
              random_state=0).fit_transform(vectors)
    xy = xy - xy.min(axis=0)
    return xy / xy.max()


def tidy_industry(text: str) -> str:
    """The SEC's industry name without its register prefix ("Services-Prepackaged Software")."""
    text = re.sub(r"^(?:services|retail|wholesale)\s*-\s*", "", " ".join(text.split()), flags=re.I)
    return text.title() if text.isupper() else text[:1].upper() + text[1:]


def tidy_name(name: str) -> str:
    """A company's name without the tag EDGAR adds to tell namesakes apart ("/DE/", "/NEW", "/ MA").

    The tag stands apart from the name or follows its legal form ("QUALCOMM INC/DE"); the slash
    of "Novo Nordisk A/S" or "InBev SA/NV" is part of the name."""
    name = re.sub(r"(?:\s+[/\\]\s*[A-Za-z]{2,4}\s*[/\\]?|[/\\])$", "", name.strip())
    return re.sub(r"(\b(?:inc|corp|co|company|ltd|limited|group|trust|plc|lp)\.?)[/\\][A-Za-z]{2,4}[/\\]?$", r"\1", name, flags=re.I)


def place_names(vectors, xy, industries: list[str], share: float = 0.3) -> list[dict]:
    """Names for the regions of the map: the industry most companies of a group share, written
    where those companies are. Groups without a clear majority get no name."""
    import numpy as np
    from sklearn.cluster import KMeans

    n = len(vectors)
    groups = KMeans(n_clusters=min(n, max(2, min(40, round(n / 40)))), n_init=10, random_state=0).fit_predict(vectors)
    best: dict[str, tuple[int, list[float]]] = {}
    for g in set(groups.tolist()):
        members = np.flatnonzero(groups == g)
        counts = Counter(industries[i] for i in members if industries[i])
        if not counts:
            continue
        name, count = counts.most_common(1)[0]
        if count < 3 or count / len(members) < share:
            continue
        where = np.median(xy[[i for i in members if industries[i] == name]], axis=0)
        if name not in best or count > best[name][0]:
            best[name] = (count, [round(float(where[0]), 4), round(float(where[1]), 4)])
    return [{"text": name, "x": xy_[0], "y": xy_[1]} for name, (_, xy_) in sorted(best.items())]


def build(k: int = PEERS_K, out: Path = PEERS_FILE, say: Callable[[str], None] = print) -> dict:
    """Neighbours, map and place names for the companies that have a vector, into ``out``."""
    import numpy as np

    stored = np.load(_vectors_path(), allow_pickle=False)
    row_of = {(int(c), str(a)): i for i, (c, a) in enumerate(zip(stored["cik"], stored["accession"]))}
    records = [r for r in load_records() if "text" in r and (r["cik"], r["accession"]) in row_of]
    vectors = unit(stored["vector"][[row_of[(r["cik"], r["accession"])] for r in records]].astype(np.float64))
    order, sims = neighbours(vectors, k)
    xy = layout(vectors)
    industries = [tidy_industry(r["industry"]) for r in records]
    companies = [{
        "ticker": r["ticker"], "tickers": r["tickers"], "name": tidy_name(r["name"]), "industry": industries[i],
        "form": r["form"], "filed": r["filed"], "url": r["url"],
        "x": round(float(xy[i, 0]), 4), "y": round(float(xy[i, 1]), 4),
        "peers": [[int(j), round(float(s), 3)] for j, s in zip(order[i], sims[i])],
    } for i, r in enumerate(records)]
    data = {"built": date.today().isoformat(), "model": str(stored["model"]), "k": k,
            "labels": place_names(vectors, xy, industries), "companies": companies}
    out.parent.mkdir(parents=True, exist_ok=True)
    # One company per line, so a rebuild shows up in git as the companies that changed.
    head = json.dumps({key: value for key, value in data.items() if key != "companies"}, ensure_ascii=False)
    rows = ",\n".join(json.dumps(c, ensure_ascii=False, separators=(",", ":")) for c in companies)
    out.write_text(f'{head[:-1]}, "companies": [\n{rows}\n]}}\n', encoding="utf-8")
    say(f"{len(companies)} companies, {len(data['labels'])} place names -> {out}")
    return data
