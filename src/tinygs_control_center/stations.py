"""SQLite-backed station catalog, independent of the MQTT radio layer."""
from dataclasses import dataclass, asdict
import math
import sqlite3
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCHEMA = """
CREATE TABLE IF NOT EXISTS stations (
 name TEXT PRIMARY KEY,
 latitude_deg REAL NOT NULL,
 longitude_deg REAL NOT NULL,
 elevation_m REAL NOT NULL,
 timezone_name TEXT NOT NULL,
 min_elevation_deg REAL NOT NULL DEFAULT 0
);
"""

@dataclass(frozen=True)
class Station:
    name: str
    latitude_deg: float
    longitude_deg: float
    elevation_m: float = 0.0
    timezone_name: str = "UTC"
    min_elevation_deg: float = 0.0

    def validate(self):
        if not self.name.strip():
            raise ValueError("Empty station name")
        for field in ("latitude_deg", "longitude_deg", "elevation_m", "min_elevation_deg"):
            if not math.isfinite(getattr(self, field)):
                raise ValueError(f"{field} must be finite")
        if not -90 <= self.latitude_deg <= 90 or not -180 <= self.longitude_deg <= 180:
            raise ValueError("Invalid station coordinates")
        if not 0 <= self.min_elevation_deg < 90:
            raise ValueError("Invalid minimum elevation")
        try:
            ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Invalid timezone") from exc

class StationStore:
    def __init__(self, connection: sqlite3.Connection):
        self.conn = connection
        self.conn.executescript(SCHEMA)

    def save(self, station: Station):
        station.validate()
        with self.conn:
            self.conn.execute("""
                INSERT INTO stations VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                latitude_deg=excluded.latitude_deg,
                longitude_deg=excluded.longitude_deg,
                elevation_m=excluded.elevation_m,
                timezone_name=excluded.timezone_name,
                min_elevation_deg=excluded.min_elevation_deg
            """, tuple(asdict(station).values()))

    def get(self, name: str):
        row = self.conn.execute("SELECT * FROM stations WHERE name = ?", (name,)).fetchone()
        return Station(**dict(row)) if row else None

    def list(self):
        return [Station(**dict(row)) for row in
                self.conn.execute("SELECT * FROM stations ORDER BY name").fetchall()]
