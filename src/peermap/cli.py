"""Command line: build the map on this machine and look at it, without the web.

    peermap fetch            step 1: each company's Business section, from the SEC
    peermap embed            step 2: one vector per company, with a model on this machine
    peermap build            step 3: neighbours and map, into src/peermap/peers.json
    peermap status           how many companies were read, and why the others were not
    peermap show NVDA        a company's neighbours on the map as built
    peermap performance      read the prices from Yahoo now and print a few returns

None of it calls a paid API.
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import PEERS_UNIVERSE, PERIODS
from .peers import PeerMap


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="peermap")
    parser.add_argument("step", choices=("fetch", "embed", "build", "status", "show", "performance"))
    parser.add_argument("ticker", nargs="?", help="for show: the company whose neighbours to print")
    parser.add_argument("--size", type=int, default=PEERS_UNIVERSE, help="fetch: how many companies to read")
    parser.add_argument("--retry", action="store_true", help="fetch: read again the companies that were skipped")
    args = parser.parse_args(argv)

    if args.step == "show":
        found = PeerMap.load().get(args.ticker or "")
        if not found:
            print("Not on the map.", file=sys.stderr)
            return 1
        print(f"{found['ticker']} - {found['name']} ({found['industry']})  {found['form']} filed {found['filed']}")
        for peer in found["peers"]:
            print(f"  {peer['similarity']:.3f}  {peer['ticker']:7} {peer['name']}  ({peer['industry']})")
        return 0
    if args.step == "performance":
        from .performance import Performance
        from .store import default_store

        tickers = [c["ticker"] for c in PeerMap.load().companies]
        doc = Performance(default_store(), tickers, ttl=0).refresh()
        print(f"as of {doc['as_of']}: {len(doc['returns'])} of {len(tickers)} companies")
        print(f"{'':8}" + "".join(f"{key:>9}" for key, _ in PERIODS))
        for ticker in tickers[:12]:
            row = doc["returns"].get(ticker) or [None] * len(PERIODS)
            print(f"{ticker:8}" + "".join(f"{'-' if v is None else format(v, '+.1%'):>9}" for v in row))
        return 0

    # Imported here: the batch is the only part that needs it.
    from . import build

    if args.step == "fetch":
        print(json.dumps(build.fetch(args.size, retry=args.retry), indent=2))
    elif args.step == "embed":
        build.embed()
    elif args.step == "build":
        build.build()
    else:
        print(json.dumps(build.summary(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
