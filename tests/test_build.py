"""Building the map: finding the Business section of a filing, and the neighbours. No network, no
model: filings are written here and the vectors come from a stand-in."""

import json

import pytest
from peermap import build as peerbuild
from peermap.build import (Listed, business_section, chunks, find_annual, latest_annual,
                                    read_company, tidy_industry, tidy_name, to_lines, universe)
from peermap.peers import PeerMap

PARAGRAPH = "We design and sell widgets to manufacturers in forty countries. " * 12


def filing(body: str) -> str:
    return f"<html><head><title>10-K</title></head><body>{body}</body></html>"


def annual_report(business: str = PARAGRAPH * 6) -> str:
    """A 10-K as they come: a table of contents with the same headings as the sections."""
    contents = "".join(f"<tr><td>{item}</td><td>{title}</td><td>{page}</td></tr>" for item, title, page in (
        ("Item 1.", "Business", 4), ("Item 1A.", "Risk Factors", 12), ("Item 2.", "Properties", 30)))
    return filing(
        "<ix:header><ix:hidden>us-gaap:Revenues 123456</ix:hidden></ix:header>"
        f"<table>{contents}</table>"
        "<div><span>Item 1.</span></div><div><span>Business</span></div>"
        f"<p>{business}</p><p>4</p><p>Table of Contents</p>"
        "<p>Item 1A. Risk Factors describes what could go wrong, and is cited here in the middle of a long "
        "sentence that is plainly not a heading of the report.</p>"
        f"<p>{PARAGRAPH}</p>"
        "<div>Item&#160;1A. Risk Factors</div><p>Our results may fall.</p>"
        "<div>Item 2. Properties</div><p>We own a plant.</p>")


def test_universe_is_one_entry_per_company_in_the_order_of_the_list():
    rows = [{"cik_str": 1, "ticker": "GOOGL", "title": "Alphabet Inc."}, {"cik_str": 2, "ticker": "MSFT", "title": "MICROSOFT CORP"},
            {"cik_str": 1, "ticker": "GOOG", "title": "Alphabet Inc."}, {"cik_str": 3, "ticker": "AAPL", "title": "Apple Inc."}]
    assert universe(rows, 2) == [Listed(1, "GOOGL", ("GOOGL", "GOOG"), "Alphabet Inc."),
                                 Listed(2, "MSFT", ("MSFT",), "MICROSOFT CORP")]


def test_the_newest_annual_report_is_picked_and_amendments_are_not():
    page = {"form": ["8-K", "10-K/A", "10-K", "10-K"], "accessionNumber": ["a-1", "a-2", "a-3", "a-4"],
            "primaryDocument": ["x.htm", "amend.htm", "new.htm", "old.htm"],
            "filingDate": ["2026-03-01", "2026-02-20", "2026-02-10", "2025-02-10"],
            "reportDate": ["", "2025-12-31", "2025-12-31", "2024-12-31"]}
    assert latest_annual(page)["document"] == "new.htm"
    assert latest_annual({"form": ["8-K"], "accessionNumber": ["a"], "primaryDocument": ["x"],
                          "filingDate": ["2026-01-01"], "reportDate": [""]}) is None


def test_a_company_that_files_every_day_has_its_annual_report_on_an_older_page():
    only_prospectuses = {"form": ["424B2"] * 3, "accessionNumber": ["p"] * 3, "primaryDocument": ["p.htm"] * 3,
                         "filingDate": ["2026-09-01"] * 3, "reportDate": [""] * 3}
    older = {"form": ["20-F"], "accessionNumber": ["f-1"], "primaryDocument": ["annual.htm"],
             "filingDate": ["2026-03-01"], "reportDate": ["2025-12-31"]}
    asked = []
    submissions = {"filings": {"recent": only_prospectuses, "files": [{"name": "CIK1-submissions-001.json"}]}}
    found = find_annual(submissions, get=lambda url: asked.append(url) or older)
    assert found["form"] == "20-F" and asked[0].endswith("CIK1-submissions-001.json")


def test_lines_drop_the_hidden_data_and_join_an_item_number_with_its_title():
    lines = to_lines(annual_report())
    assert not any("us-gaap" in line for line in lines)
    assert "Item 1. Business" in lines and "Item 1A. Risk Factors" in lines
    assert "4" not in lines and "Table of Contents" not in lines


def test_the_business_section_is_the_long_stretch_not_the_table_of_contents():
    text = business_section(to_lines(annual_report()))
    assert text.startswith("We design and sell widgets")
    # A sentence that starts with "Item 1A" does not end the section; the heading does.
    assert "plainly not a heading" in text
    assert "Our results may fall" not in text and "We own a plant" not in text


def test_a_report_that_only_points_to_other_pages_has_no_business_section():
    index = filing("<p>Item 1. Business 4-7, 9-10</p><p>Item 1A. Risk Factors 24-31</p>" + f"<p>{PARAGRAPH}</p>" * 6)
    assert business_section(to_lines(index)) is None
    # A heading with nothing after it that closes the section is not taken to the end of the report.
    assert business_section(to_lines(filing("<p>Item 1. Business</p>" + f"<p>{PARAGRAPH}</p>" * 6))) is None


def test_headings_without_item_numbers_and_the_foreign_annual_report():
    plain = filing("<p>Business</p><p>Risk Factors</p><h2>Business</h2>" + f"<p>{PARAGRAPH}</p>" * 6 + "<h2>Risk Factors</h2><p>Risks.</p>")
    assert business_section(to_lines(plain)).count("widgets") == 72
    foreign = filing("<p>ITEM 4. INFORMATION ON THE COMPANY</p>" + f"<p>{PARAGRAPH}</p>" * 6 + "<p>ITEM 4A. UNRESOLVED STAFF COMMENTS</p><p>None.</p>")
    assert business_section(to_lines(foreign), "20-F").startswith("We design")
    assert business_section(to_lines(foreign), "10-K") is None


@pytest.mark.parametrize("opening, closing", [
    ("Part I. Item 1. Business", "Part I. Item 1A. Risk Factors"),  # Expedia
    ("ITEM 1 | Business", "ITEM 1A | Risk Factors"),  # AIG, on every page of the section
    ("ITEM 1. General", "ITEM 1A. RISK FACTORS"),  # Exelon
    ("Items 1 and 2. Business and Properties", "Item 1A. Risk Factors"),  # oil and gas producers
    ("BUSINESS SUMMARY", "RISK FACTORS"),  # McDonald's
])
def test_the_headings_real_reports_use(opening, closing):
    body = f"<p>{opening}</p>" + f"<p>{PARAGRAPH}</p>" * 6 + f"<p>{closing}</p><p>Our results may fall.</p>"
    text = business_section(to_lines(filing(body)))
    assert text.count("widgets") == 72 and "may fall" not in text


def test_a_foreign_report_that_breaks_the_heading_or_names_the_company():
    for opening in ("Item 4. Information</p><p>on the Company", "ITEM 4. INFORMATION ON CHECK POINT"):
        body = f"<p>{opening}</p>" + f"<p>{PARAGRAPH}</p>" * 6 + "<p>Item 4A. Unresolved</p><p>None.</p>"
        assert business_section(to_lines(filing(body)), "20-F").count("widgets") == 72


def test_pieces_fit_the_model_and_lose_nothing():
    text = "\n".join([PARAGRAPH, "Short paragraph.", "A sentence of some length. " * 200, "The end."])
    pieces = chunks(text, 400)
    assert all(0 < len(p) <= 400 for p in pieces)
    assert "".join(pieces).replace("\n", "").replace(" ", "") == text.replace("\n", "").replace(" ", "")


def test_names_as_the_page_shows_them():
    assert tidy_industry("Services-Prepackaged Software") == "Prepackaged Software"
    assert tidy_industry("STATE COMMERCIAL BANKS") == "State Commercial Banks"
    assert tidy_name("BANK OF AMERICA CORP /DE/") == "BANK OF AMERICA CORP"
    assert tidy_name("COSTCO WHOLESALE CORP /NEW") == "COSTCO WHOLESALE CORP"
    assert tidy_name("US BANCORP \\DE\\") == "US BANCORP" and tidy_name("TOYOTA MOTOR CORP/") == "TOYOTA MOTOR CORP"
    assert tidy_name("Rivian Automotive, Inc. / DE") == "Rivian Automotive, Inc."
    assert tidy_name("QUALCOMM INC/DE") == "QUALCOMM INC" and tidy_name("Anheuser-Busch InBev SA/NV") == "Anheuser-Busch InBev SA/NV"
    assert tidy_name("NOVO NORDISK A/S") == "NOVO NORDISK A/S" and tidy_name("M/I HOMES, INC.") == "M/I HOMES, INC."
    assert tidy_name("Apple Inc.") == "Apple Inc."
    assert tidy_industry("Retail-Eating  Places") == "Eating Places"


def submissions_for(name: str, industry: str) -> dict:
    return {"name": name, "sic": "3674", "sicDescription": industry, "filings": {"recent": {
        "form": ["10-K"], "accessionNumber": ["0000000001-26-000001"], "primaryDocument": ["annual.htm"],
        "filingDate": ["2026-02-01"], "reportDate": ["2025-12-31"]}, "files": []}}


def test_a_company_record_says_what_was_read_or_why_not():
    company = Listed(7, "WDGT", ("WDGT",), "WIDGET CORP")
    record = read_company(company, get=lambda url: submissions_for("WIDGET CORP", "Semiconductors & Related Devices"),
                          get_text=lambda url: annual_report())
    assert record["url"] == "https://www.sec.gov/Archives/edgar/data/7/000000000126000001/annual.htm"
    assert record["form"] == "10-K" and record["filed"] == "2026-02-01" and record["text"].startswith("We design")
    empty = read_company(company, get=lambda url: {"name": "WIDGET CORP", "filings": {"recent": {}, "files": []}})
    assert empty["skipped"] == "no 10-K or 20-F on file" and "text" not in empty
    pointer = read_company(company, get=lambda url: submissions_for("WIDGET CORP", ""),
                           get_text=lambda url: filing("<p>See the annual report.</p>"))
    assert pointer["skipped"].startswith("no Business section") and pointer["url"]


def test_neighbours_are_the_most_alike_once_what_all_share_is_removed():
    np = pytest.importorskip("numpy")
    shared = np.array([10.0, 10.0, 10.0])  # what every annual report says
    chips, banks = np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])
    vectors = np.array([shared + chips, shared + chips * 0.9 + banks * 0.1, shared + banks, shared + banks * 0.9 + chips * 0.1])
    order, sims = peerbuild.neighbours(peerbuild.unit(vectors), k=2)
    assert order[:, 0].tolist() == [1, 0, 3, 2]
    assert all(sims[i, 0] > sims[i, 1] for i in range(4)) and sims[0, 0] > 0.9 and sims[0, 1] < 0


def test_the_batch_end_to_end_with_a_stand_in_model(tmp_path, monkeypatch):
    np = pytest.importorskip("numpy")
    pytest.importorskip("sklearn")
    monkeypatch.setattr(peerbuild, "WORK_DIR", tmp_path)
    kinds = {"chips": [1.0, 0.0, 0.0], "banks": [0.0, 1.0, 0.0], "drugs": [0.0, 0.0, 1.0]}
    industries = {"chips": "Semiconductors & Related Devices", "banks": "STATE COMMERCIAL BANKS", "drugs": "Pharmaceutical Preparations"}
    (tmp_path / "text").mkdir()
    ciks = []
    for k, kind in enumerate(kinds):
        for n in range(4):
            cik = 100 * (k + 1) + n
            ciks.append(cik)
            record = {"cik": cik, "ticker": f"{kind[:2].upper()}{n}", "tickers": [f"{kind[:2].upper()}{n}", f"{kind[:2].upper()}{n}-B"],
                      "name": f"{kind} {n} CORP /DE/", "sic": "1", "industry": industries[kind], "form": "10-K",
                      "accession": f"acc-{cik}", "document": "a.htm", "filed": "2026-02-01", "period": "2025-12-31",
                      "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/a.htm", "text": f"{kind} {n} " + PARAGRAPH}
            (tmp_path / "text" / f"{cik}.json").write_text(json.dumps(record), encoding="utf-8")
    skipped = {"cik": 999, "ticker": "NONE", "tickers": ["NONE"], "name": "NONE", "sic": "", "industry": "", "skipped": "no 10-K or 20-F on file"}
    (tmp_path / "text" / "999.json").write_text(json.dumps(skipped), encoding="utf-8")
    (tmp_path / "universe.json").write_text(json.dumps(ciks + [999]))

    calls = []

    def encode(texts):
        calls.append(len(texts))
        kind, n = texts[0].split()[:2]
        return np.array([[5.0, 5.0, 5.0]] * len(texts)) + np.array(kinds[kind]) + 0.01 * int(n)

    assert peerbuild.embed(model="stand-in", say=lambda _: None, encode=encode) == 12
    assert peerbuild.embed(model="stand-in", say=lambda _: None, encode=encode) == 0  # nothing new: nothing embedded
    assert len(calls) == 12

    out = tmp_path / "peers.json"
    data = peerbuild.build(k=3, out=out, say=lambda _: None)
    assert json.loads(out.read_text(encoding="utf-8")) == data
    assert len(data["companies"]) == 12 and data["model"] == "stand-in"
    peers = PeerMap(data)
    chip = peers.get("ch0-b")  # any share class finds the company
    assert chip["ticker"] == "CH0" and chip["name"] == "chips 0 CORP"
    assert {p["ticker"] for p in chip["peers"]} == {"CH1", "CH2", "CH3"}
    assert chip["peers"][0]["similarity"] >= chip["peers"][-1]["similarity"]
    assert all(0 <= c["x"] <= 1 and 0 <= c["y"] <= 1 for c in data["companies"])
    assert {l["text"] for l in data["labels"]} <= {"Semiconductors & Related Devices", "State Commercial Banks", "Pharmaceutical Preparations"}
    assert peers.get("NONE") is None
