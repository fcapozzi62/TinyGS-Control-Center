"""CLI for the first experimental catalog release."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from .stations import Station, StationStore
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
    station = commands.add_parser("station-add", help="Create or update a ground station")
    station.add_argument("name")
    station.add_argument("--lat", type=float, required=True)
    station.add_argument("--lon", type=float, required=True)
    station.add_argument("--elevation-m", type=float, default=0.0)
    station.add_argument("--timezone", default="UTC")
    station.add_argument("--min-elevation", type=float, default=0.0)
    commands.add_parser("stations", help="List ground stations")

    passes = commands.add_parser("passes", help="Predict satellite pass events")
    passes.add_argument("norad", type=int)
    passes.add_argument("--station", required=True)
    passes.add_argument("--start", help="ISO-8601 aware start, e.g. 2026-11-01T00:00:00Z")
    passes.add_argument("--hours", type=float, default=24.0)
    passes.add_argument("--freq-mhz", type=float)
    doppler = commands.add_parser("doppler", help="Sample Doppler throughout predicted passes")
    doppler.add_argument("norad", type=int)
    doppler.add_argument("--station", required=True)
    doppler.add_argument("--start", help="Timezone-aware ISO-8601 start")
    doppler.add_argument("--hours", type=float, default=24.0)
    doppler.add_argument("--freq-mhz", type=float, required=True)
    doppler.add_argument("--step-sec", type=int, default=60)
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
            if args.command == "station-add":
                new = Station(args.name, args.lat, args.lon, args.elevation_m,
                              args.timezone, args.min_elevation)
                StationStore(catalog.conn).save(new)
                print(f"Station saved: {new.name}")
                return 0
            if args.command == "stations":
                from dataclasses import asdict
                items = [asdict(s) for s in StationStore(catalog.conn).list()]
                print(json.dumps(items, indent=2))
                return 0
            if args.command == "doppler":
                from .orbital import doppler_profile, predict_passes
                site = StationStore(catalog.conn).get(args.station)
                if site is None:
                    raise ValueError(f"Station not found: {args.station}")
                entry = catalog.latest(args.norad)
                if entry is None:
                    raise ValueError(f"Satellite NORAD {args.norad} not found")
                start = (datetime.fromisoformat(args.start.replace("Z", "+00:00"))
                         if args.start else datetime.now(timezone.utc))
                passes = predict_passes(entry["omm"], site, start, args.hours, args.freq_mhz)
                results = []
                for p in passes:
                    parse = datetime.fromisoformat
                    series = doppler_profile(
                        entry["omm"], site,
                        parse(p.aos_utc), parse(p.tca_utc), parse(p.los_utc),
                        args.freq_mhz, args.step_sec,
                    )
                    results.append({"tca_local": p.tca_local,
                                    "max_elevation_deg": p.max_elevation_deg,
                                    "samples": series})
                print(json.dumps({"norad_cat_id": args.norad, "station": site.name,
                                  "source": entry["source"], "epoch": entry["epoch"],
                                  "carrier_mhz": args.freq_mhz,
                                  "step_seconds": args.step_sec,
                                  "passes": results}, indent=2))
                return 0
            if args.command == "passes":
                from .orbital import predict_passes
                site = StationStore(catalog.conn).get(args.station)
                if site is None:
                    raise ValueError(f"Station not found: {args.station}")
                entry = catalog.latest(args.norad)
                if entry is None:
                    raise ValueError(f"Satellite NORAD {args.norad} not found")
                start = (datetime.fromisoformat(args.start.replace("Z", "+00:00"))
                         if args.start else datetime.now(timezone.utc))
                rows = predict_passes(entry["omm"], site, start, args.hours, args.freq_mhz)
                print(json.dumps({"norad_cat_id": args.norad, "station": site.name,
                                  "source": entry["source"], "epoch": entry["epoch"],
                                  "passes": [p.as_dict() for p in rows]}, indent=2))
                return 0
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
