"""CLI for the first experimental catalog release."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import __version__
from .catalog import OrbitalCatalog, parse_omm_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TinyGS Control Center (experimental)")
    parser.add_argument("--db", type=Path, default=Path("data/catalog.sqlite"))
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    imp = commands.add_parser("import-omm", help="Import OMM JSON from a local file")
    imp.add_argument("path", type=Path)
    imp.add_argument("--source", default="local")

    fetch = commands.add_parser("fetch-omm", help="Fetch OMM JSON from CelesTrak")
    fetch.add_argument("norad", type=int)

    commands.add_parser("list", help="List imported satellites")
    show = commands.add_parser("show", help="Show latest stored elements by NORAD ID")
    show.add_argument("norad", type=int)
    return parser


def fetch_celestrak(norad: int) -> list[dict]:
    if norad <= 0:
        raise ValueError("NORAD ID must be positive")
    url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={norad}&FORMAT=JSON"
    request = Request(url, headers={"User-Agent": "TinyGS-Control-Center/0.0.1"})
    with urlopen(request, timeout=20) as response:
        payload = response.read(2_000_001)
    if len(payload) > 2_000_000:
        raise ValueError("OMM response exceeds 2 MB")
    records = parse_omm_json(payload.decode("utf-8"))
    if not records:
        raise ValueError(f"No orbital elements returned for NORAD {norad}")
    if len(records) != 1 or int(records[0].get("NORAD_CAT_ID", 0)) != norad:
        raise ValueError("CelesTrak response does not match requested NORAD ID")
    return records


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "fetch-omm":
            records = fetch_celestrak(args.norad)
            source = "celestrak"
        elif args.command == "import-omm":
            records = parse_omm_json(args.path.read_text(encoding="utf-8"))
            source = args.source
        else:
            records = None
            source = ""

        with OrbitalCatalog(args.db) as catalog:
            if records is not None:
                seen, inserted = catalog.import_records(records, source)
                print(f"OMM: {seen} received, {inserted} new element sets stored")
            elif args.command == "list":
                print(json.dumps(catalog.list_satellites(), indent=2))
            elif args.command == "show":
                obj = catalog.latest(args.norad)
                if obj is None:
                    print(f"NORAD {args.norad} not found", file=sys.stderr)
                    return 1
                print(json.dumps(obj, indent=2))
        return 0
    except (ValueError, OSError, HTTPError, URLError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
