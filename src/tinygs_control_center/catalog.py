"""Minimal OMM JSON validation and SQLite persistence.

The OMM objects are kept intact as JSON. Only a few frequently queried fields
are materialized. No TLE conversion or provisional NORAD remapping occurs here.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS satellites (
    id INTEGER PRIMARY KEY,
    norad_cat_id INTEGER NOT NULL UNIQUE CHECK (norad_cat_id > 0),
    object_name TEXT NOT NULL,
    object_id TEXT
);

CREATE TABLE IF NOT EXISTS orbital_elements (
    id INTEGER PRIMARY KEY,
    satellite_id INTEGER NOT NULL REFERENCES satellites(id),
    source TEXT NOT NULL,
    epoch TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    mean_motion REAL NOT NULL,
    inclination REAL NOT NULL,
    eccentricity REAL NOT NULL,
    omm_json TEXT NOT NULL CHECK (json_valid(omm_json)),
    UNIQUE (satellite_id, source, epoch)
);

CREATE INDEX IF NOT EXISTS idx_orbital_epoch
    ON orbital_elements(satellite_id, epoch DESC);
"""


def _utc_timestamp(value: str) -> str:
    """Normalize an ISO-8601 epoch to lexically sortable UTC text."""
    if not isinstance(value, str):
        raise ValueError("EPOCH must be an ISO-8601 string")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid OMM EPOCH: {value!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # CelesTrak OMM JSON uses UTC
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _number(record: Mapping[str, Any], key: str) -> float:
    value = record.get(key)
    if isinstance(value, bool):
        raise ValueError(f"{key} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{key} must be finite")
    return result


def validate_omm(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the fields needed for an orbital catalog; preserve all fields."""
    if not isinstance(record, dict):
        raise ValueError("Each OMM record must be a JSON object")
    try:
        raw_id = record["NORAD_CAT_ID"]
        if isinstance(raw_id, bool) or str(raw_id).strip() != str(int(raw_id)):
            raise ValueError
        norad = int(raw_id)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("NORAD_CAT_ID must be a positive integer") from exc
    if norad <= 0:
        raise ValueError("NORAD_CAT_ID must be a positive integer")
    name = record.get("OBJECT_NAME")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("OBJECT_NAME must be a non-empty string")
    epoch = _utc_timestamp(record.get("EPOCH"))
    mean_motion = _number(record, "MEAN_MOTION")
    eccentricity = _number(record, "ECCENTRICITY")
    inclination = _number(record, "INCLINATION")
    if mean_motion <= 0 or not (0 <= eccentricity < 1) or not (0 <= inclination <= 180):
        raise ValueError("Invalid orbital element range")
    object_id = record.get("OBJECT_ID")
    if object_id is not None and not isinstance(object_id, str):
        raise ValueError("OBJECT_ID must be a string when provided")
    return {
        "norad": norad,
        "name": name.strip(),
        "object_id": object_id,
        "epoch": epoch,
        "mean_motion": mean_motion,
        "inclination": inclination,
        "eccentricity": eccentricity,
    }


class OrbitalCatalog:
    def __init__(self, database: str | Path):
        self.path = Path(database)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "OrbitalCatalog":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def import_records(self, records: list[dict[str, Any]], source: str) -> tuple[int, int]:
        """Import atomically. Returns (records seen, new element sets inserted)."""
        if not source or not source.strip():
            raise ValueError("Source cannot be empty")
        validated = [(record, validate_omm(record)) for record in records]
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        inserted = 0
        with self.conn:
            for record, info in validated:
                self.conn.execute(
                    """INSERT INTO satellites (norad_cat_id, object_name, object_id)
                       VALUES (?, ?, ?)
                       ON CONFLICT(norad_cat_id) DO UPDATE SET
                       object_name=excluded.object_name,
                       object_id=COALESCE(excluded.object_id, satellites.object_id)""",
                    (info["norad"], info["name"], info["object_id"]),
                )
                sat = self.conn.execute(
                    "SELECT id FROM satellites WHERE norad_cat_id = ?",
                    (info["norad"],),
                ).fetchone()
                cursor = self.conn.execute(
                    """INSERT OR IGNORE INTO orbital_elements
                       (satellite_id, source, epoch, fetched_at, mean_motion,
                        inclination, eccentricity, omm_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        sat["id"], source.strip(), info["epoch"], now,
                        info["mean_motion"], info["inclination"],
                        info["eccentricity"],
                        json.dumps(record, ensure_ascii=False, allow_nan=False),
                    ),
                )
                inserted += cursor.rowcount
        return len(validated), inserted

    def list_satellites(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT s.norad_cat_id, s.object_name, s.object_id,
                      COUNT(e.id) AS element_sets, MAX(e.epoch) AS latest_epoch
               FROM satellites AS s
               LEFT JOIN orbital_elements AS e ON e.satellite_id = s.id
               GROUP BY s.id ORDER BY s.object_name"""
        ).fetchall()
        return [dict(row) for row in rows]

    def latest(self, norad: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            """SELECT s.norad_cat_id, s.object_name, e.source, e.epoch,
                      e.fetched_at, e.omm_json
               FROM satellites s
               JOIN orbital_elements e ON e.satellite_id = s.id
               WHERE s.norad_cat_id = ?
               ORDER BY e.epoch DESC, e.fetched_at DESC LIMIT 1""",
            (norad,),
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["omm"] = json.loads(result.pop("omm_json"))
        return result


def parse_omm_json(content: str) -> list[dict[str, Any]]:
    obj = json.loads(content)
    if isinstance(obj, dict):
        return [obj]
    if isinstance(obj, list) and all(isinstance(item, dict) for item in obj):
        return obj
    raise ValueError("Expected an OMM JSON object or array of objects")
