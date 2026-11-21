"""TinyGS MQTT telemetry normalization and ephemeral per-station registry.

This module does not connect to a broker, persist data, or transmit commands.
A station MQTT name is distinct from an orbital catalog station name.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math


_ALLOWED_KINDS = {("tele", "welcome"), ("tele", "rx"), ("stat", "status"), ("cmnd", "begine")}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _string(value):
    return value if isinstance(value, str) else None


def _positive_int(value):
    return value if type(value) is int and value > 0 else None


def decode_station_message(topic: str, payload: bytes, *,
                           received_at: datetime | None = None) -> dict | None:
    """Normalize selected TinyGS telemetry topics; ignore everything else.

    Invalid/truncated JSON is ignored. Unknown fields are not preserved:
    in particular RX raw data, MAC/IP, configuration and credentials are never
    copied into registry snapshots.
    """
    parts = topic.split("/")
    if (len(parts) != 5 or parts[0] != "tinygs" or not parts[1] or
            not parts[2] or (parts[3], parts[4]) not in _ALLOWED_KINDS):
        return None
    if len(payload) > 65536:
        return None
    try:
        body = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeError):
        return None
    if not isinstance(body, dict):
        return None
    now = received_at or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("received_at must be timezone-aware")
    event = {
        "mqtt_user": parts[1],
        "station_name": parts[2],
        "kind": "/".join(parts[3:]),
        "received_at_utc": now.astimezone(timezone.utc).isoformat(),
    }
    if event["kind"] == "cmnd/begine":
        # This is a requested tuning profile, NOT proof that the radio applied it.
        event["satellite"] = _string(body.get("sat"))
        event["norad_cat_id"] = _positive_int(body.get("NORAD"))
        event["mode"] = _string(body.get("mode"))
        event["frequency_mhz"] = _number(body.get("freq"))
        # Parse only radio profile fields; never retain base64 'tlx' or filters.
        for field in ("bw", "sf", "cr", "sw", "pl"):
            event[field] = _number(body.get(field))
    elif event["kind"] == "tele/welcome":
        event["satellite"] = _string(body.get("sat"))
        event["firmware_version"] = _positive_int(body.get("version"))
    else:
        event["satellite"] = _string(body.get("satellite"))
        event["norad_cat_id"] = _positive_int(body.get("NORAD"))
        event["mode"] = _string(body.get("mode"))
        event["frequency_mhz"] = _number(body.get("frequency"))
        event["frequency_offset_hz"] = _number(body.get("frequency_offset"))
        if event["kind"] == "tele/rx":
            event["doppler_hz"] = _number(body.get("f_doppler"))
            event["rssi_dbm"] = _number(body.get("rssi"))
            event["snr_db"] = _number(body.get("snr"))
            event["frequency_error_hz"] = _number(body.get("frequency_error"))
            event["crc_error"] = body.get("crc_error") if type(body.get("crc_error")) is bool else None
            event["noisy"] = body.get("noisy") if type(body.get("noisy")) is bool else None
    return event


@dataclass
class StationSnapshot:
    mqtt_user: str
    station_name: str
    last_seen_utc: str | None = None
    last_event: str | None = None
    last_welcome_utc: str | None = None
    last_status_utc: str | None = None
    last_rx_utc: str | None = None
    firmware_version: int | None = None
    satellite: str | None = None
    norad_cat_id: int | None = None
    mode: str | None = None
    frequency_mhz: float | None = None
    frequency_offset_hz: float | None = None
    doppler_hz: float | None = None
    rssi_dbm: float | None = None
    snr_db: float | None = None
    frequency_error_hz: float | None = None
    last_command_utc: str | None = None
    command_count: int = 0
    commanded_satellite: str | None = None
    commanded_norad_cat_id: int | None = None
    commanded_mode: str | None = None
    commanded_frequency_mhz: float | None = None
    commanded_bw: float | None = None
    commanded_sf: float | None = None
    commanded_cr: float | None = None
    commanded_sw: float | None = None
    commanded_pl: float | None = None
    status_satellite: str | None = None
    status_norad_cat_id: int | None = None
    status_mode: str | None = None
    status_frequency_mhz: float | None = None
    last_rx_satellite: str | None = None
    last_rx_norad_cat_id: int | None = None
    last_rx_mode: str | None = None
    last_rx_frequency_mhz: float | None = None
    rx_count: int = 0
    crc_error_count: int = 0
    noisy_count: int = 0

    def to_dict(self) -> dict:
        result = asdict(self)
        result["presence"] = "observed_only"
        return result


class StationRegistry:
    """Ephemeral registry keyed by (MQTT account, MQTT station identifier).

    A message's receive timestamp reflects when the monitor saw it; no
    message is treated as proof of current device connectivity.
    """

    def __init__(self):
        self._stations: dict[tuple[str, str], StationSnapshot] = {}

    def ingest(self, topic: str, payload: bytes, *,
               received_at: datetime | None = None) -> dict | None:
        event = decode_station_message(topic, payload, received_at=received_at)
        if event is None:
            return None
        key = (event["mqtt_user"], event["station_name"])
        state = self._stations.setdefault(key, StationSnapshot(*key))
        at = event["received_at_utc"]
        kind = event["kind"]
        # Ignore out-of-order updates to avoid overwriting current state.
        if state.last_seen_utc is not None and at < state.last_seen_utc:
            return None
        state.last_seen_utc = at
        state.last_event = kind
        if kind == "cmnd/begine":
            state.last_command_utc = at
            state.command_count += 1
            for source, dest in (
                ("satellite", "commanded_satellite"),
                ("norad_cat_id", "commanded_norad_cat_id"),
                ("mode", "commanded_mode"),
                ("frequency_mhz", "commanded_frequency_mhz"),
                ("bw", "commanded_bw"), ("sf", "commanded_sf"),
                ("cr", "commanded_cr"), ("sw", "commanded_sw"),
                ("pl", "commanded_pl"),
            ):
                # Reset fields absent in a new command: no stale LoRa settings on FSK.
                setattr(state, dest, event.get(source))
        if kind == "tele/welcome":
            state.last_welcome_utc = at
        if kind == "stat/status":
            state.last_status_utc = at
            for source, dest in (
                ("satellite", "status_satellite"),
                ("norad_cat_id", "status_norad_cat_id"),
                ("mode", "status_mode"),
                ("frequency_mhz", "status_frequency_mhz"),
            ):
                setattr(state, dest, event.get(source))
        if kind == "tele/rx":
            state.last_rx_utc = at
            state.rx_count += 1
            for source, dest in (
                ("satellite", "last_rx_satellite"),
                ("norad_cat_id", "last_rx_norad_cat_id"),
                ("mode", "last_rx_mode"),
                ("frequency_mhz", "last_rx_frequency_mhz"),
            ):
                setattr(state, dest, event.get(source))
            if event.get("crc_error") is True:
                state.crc_error_count += 1
            if event.get("noisy") is True:
                state.noisy_count += 1
        # Legacy "latest observed" fields retain previous behavior for existing
        # clients, but a command cannot overwrite the observed radio state.
        if kind != "cmnd/begine":
            for field in (
                "firmware_version", "satellite", "norad_cat_id", "mode",
                "frequency_mhz", "frequency_offset_hz", "doppler_hz",
                "rssi_dbm", "snr_db", "frequency_error_hz",
            ):
                if event.get(field) is not None:
                    setattr(state, field, event[field])
        return event

    def snapshots(self) -> list[dict]:
        return [self._stations[k].to_dict() for k in sorted(self._stations)]
