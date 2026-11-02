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
    replay = commands.add_parser(
        "telemetry-replay", help="Build station snapshots from offline JSONL MQTT messages"
    )
    replay.add_argument("path", type=Path, help="JSONL with topic and payload JSON")
    mqtt_monitor = commands.add_parser(
        "mqtt-monitor", help="Read MQTT telemetry only, never publish commands"
    )
    mqtt_monitor.add_argument("--host", required=True, help="MQTT broker hostname/IP")
    mqtt_monitor.add_argument("--port", type=int, default=1883)
    mqtt_monitor.add_argument("--mqtt-user", required=True)
    mqtt_monitor.add_argument("--topic", default="tinygs/#")
    mqtt_monitor.add_argument("--timeout-sec", type=float, default=30.0)
    mqtt_monitor.add_argument("--max-messages", type=int, default=0)
    mqtt_monitor.add_argument("--summarize-stations", action="store_true",
                              help="Print observed TinyGS station snapshots on exit")
    mqtt_dry = commands.add_parser(
        "mqtt-dry-run", help="Preview TinyGS Doppler foff message (no network)"
    )
    mqtt_dry.add_argument("--mqtt-user", required=True,
                          help="MQTT account topic identifier, not a password")
    mqtt_dry.add_argument("--station", required=True,
                          help="TinyGS MQTT station name")
    mqtt_dry.add_argument("--offset-hz", type=float, required=True,
                          help="Known receiver calibration offset in Hz (mandatory)")
    mqtt_dry.add_argument("--tolerance-hz", type=int, required=True,
                          help="Doppler retune threshold in Hz, 1..65535")
    mqtt_dry.add_argument("--refresh-ms", type=int, required=True,
                          help="Firmware Doppler refresh period in ms, 1..65535")
    simulation = commands.add_parser(
        "simulate-doppler", help="Offline threshold-based retune comparison"
    )
    simulation.add_argument("norad", type=int)
    simulation.add_argument("--station", required=True)
    simulation.add_argument("--start", help="Timezone-aware ISO-8601 start")
    simulation.add_argument("--hours", type=float, default=24.0)
    simulation.add_argument("--freq-mhz", type=float, required=True)
    simulation.add_argument("--thresholds", type=float, nargs="+",
                            default=[100.0, 250.0, 500.0],
                            help="One or more residual-frequency thresholds in Hz")
    simulation.add_argument("--step-sec", type=int, default=1,
                            help="Virtual clock sample cadence (default: 1 second)")
    simulation.add_argument("--busy-period-sec", type=int, default=0,
                            help="Synthetic periodic packet activity, 0 disables")
    simulation.add_argument("--busy-duration-sec", type=int, default=0,
                            help="Synthetic busy duration at each period start")
    simulation.add_argument("--with-tinygs-legacy", action="store_true",
                            help="Include original TinyGS 4s/1200Hz algorithm")
    simulation.add_argument("--legacy-refresh-sec", type=float, default=4.0)
    simulation.add_argument("--legacy-tolerance-hz", type=float, default=1200.0)
    simulation.add_argument("--with-rf-model", action="store_true",
                            help="Include SX1262-inspired offline RF model")
    simulation.add_argument("--rf-latency-ms", type=float, default=6.2)
    simulation.add_argument("--rf-step-hz", type=float,
                            default=32_000_000 / (2 ** 25))
    simulation.add_argument("--rf-packet-period-sec", type=float, default=0.0)
    simulation.add_argument("--rf-packet-duration-ms", type=float, default=0.0)
    simulation.add_argument("--rf-no-defer", action="store_true",
                            help="Allow RF retunes while a synthetic packet is active")
    simulation.add_argument("--show-retunes", action="store_true",
                            help="Include all hypothetical retune events")
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
        if args.command == "telemetry-replay":
            from .telemetry import StationRegistry
            registry = StationRegistry()
            for line_num, line in enumerate(
                    args.path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise ValueError("expected JSON object")
                    topic = record["topic"]
                    payload = record["payload"]
                    if not isinstance(topic, str) or not isinstance(payload, dict):
                        raise ValueError("topic must be a string, payload a JSON object")
                    at = record.get("received_at_utc")
                    instant = (datetime.fromisoformat(at.replace("Z", "+00:00"))
                               if isinstance(at, str) else None)
                    registry.ingest(
                        topic, json.dumps(payload).encode("utf-8"),
                        received_at=instant,
                    )
                except (KeyError, ValueError, TypeError) as exc:
                    raise ValueError(f"Invalid replay line {line_num}: {exc}") from exc
            print(json.dumps(registry.snapshots(), indent=2))
            return 0
        if args.command == "mqtt-monitor":
            import os
            from .mqtt_monitor import monitor
            password = os.environ.get("TCC_MQTT_PASSWORD", "")
            if not password:
                raise ValueError("TCC_MQTT_PASSWORD environment variable is required")
            return monitor(args.host, args.port, args.mqtt_user, password,
                           args.topic, args.timeout_sec, args.max_messages,
                           args.summarize_stations)
        if args.command == "mqtt-dry-run":
            from .mqtt_adapter import DopplerConfig, build_foff_dry_run
            preview = build_foff_dry_run(
                args.mqtt_user, args.station,
                DopplerConfig(args.offset_hz, args.tolerance_hz, args.refresh_ms),
            )
            print(json.dumps(preview, indent=2))
            return 0
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
            if args.command == "simulate-doppler":
                from .orbital import doppler_profile, predict_passes
                from .simulator import simulate_threshold, simulate_tinygs_legacy
                site = StationStore(catalog.conn).get(args.station)
                if site is None:
                    raise ValueError(f"Station not found: {args.station}")
                entry = catalog.latest(args.norad)
                if entry is None:
                    raise ValueError(f"Satellite NORAD {args.norad} not found")
                start = (datetime.fromisoformat(args.start.replace("Z", "+00:00"))
                         if args.start else datetime.now(timezone.utc))
                if not 1 <= args.step_sec <= 60:
                    raise ValueError("Simulation step must be between 1 and 60 seconds")
                # The simulator has a virtual clock: it never sleeps or sends MQTT.
                windows = predict_passes(entry["omm"], site, start,
                                         args.hours, args.freq_mhz)
                simulations = []
                for p in windows:
                    parse = datetime.fromisoformat
                    samples = doppler_profile(
                        entry["omm"], site, parse(p.aos_utc), parse(p.tca_utc),
                        parse(p.los_utc), args.freq_mhz, args.step_sec)
                    strategies = []
                    for threshold in args.thresholds:
                        result = simulate_threshold(
                            samples, threshold,
                            busy_period_s=args.busy_period_sec,
                            busy_duration_s=args.busy_duration_sec)
                        if not args.show_retunes:
                            result.pop("retunes")
                        strategies.append(result)
                    if args.with_rf_model:
                        from .rf_simulator import simulate_rf
                        for threshold in args.thresholds:
                            rf = simulate_rf(
                                samples, threshold, args.freq_mhz,
                                latency_ms=args.rf_latency_ms,
                                synthesizer_step_hz=args.rf_step_hz,
                                packet_period_s=args.rf_packet_period_sec,
                                packet_duration_ms=args.rf_packet_duration_ms,
                                defer_while_busy=not args.rf_no_defer)
                            if not args.show_retunes:
                                rf.pop("retunes")
                            strategies.append(rf)
                    if args.with_tinygs_legacy:
                        legacy = simulate_tinygs_legacy(
                            samples, tolerance_hz=args.legacy_tolerance_hz,
                            refresh_s=args.legacy_refresh_sec)
                        if not args.show_retunes:
                            legacy.pop("retunes")
                        strategies.append(legacy)
                    simulations.append({
                        "aos_local": p.aos_local,
                        "tca_local": p.tca_local,
                        "los_local": p.los_local,
                        "max_elevation_deg": p.max_elevation_deg,
                        "strategies": strategies
                    })
                print(json.dumps({
                    "norad_cat_id": args.norad, "station": site.name,
                    "source": entry["source"], "epoch": entry["epoch"],
                    "carrier_mhz": args.freq_mhz,
                    "sample_step_seconds": args.step_sec,
                    "model": "offline_ideal_instantaneous_retune",
                    "passes": simulations
                }, indent=2))
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
