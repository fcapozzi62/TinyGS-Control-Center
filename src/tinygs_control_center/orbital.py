"""Offline OMM-based satellite pass prediction via Skyfield/SGP4."""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import math
from zoneinfo import ZoneInfo

from skyfield.api import EarthSatellite, load, wgs84
from .stations import Station

SPEED_OF_LIGHT_KM_S = 299792.458

@dataclass(frozen=True)
class Pass:
    aos_utc: str
    tca_utc: str
    los_utc: str
    aos_local: str
    tca_local: str
    los_local: str
    max_elevation_deg: float
    aos_azimuth_deg: float
    tca_azimuth_deg: float
    los_azimuth_deg: float
    doppler_hz_at_tca: float | None
    element_epoch_utc: str
    element_age_days_at_tca: float

    def as_dict(self):
        return asdict(self)

def predict_passes(omm: dict, station: Station, start: datetime,
                   hours: float = 24.0, carrier_mhz: float | None = None) -> list[Pass]:
    """Return complete passes within the requested interval.

    Only complete rise/culminate/set triples are returned; boundary passes
    are intentionally omitted for this first implementation.
    """
    station.validate()
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError("Start must include a timezone")
    if not math.isfinite(hours) or not 0 < hours <= 168:
        raise ValueError("hours must be within (0, 168]")
    if carrier_mhz is not None and (not math.isfinite(carrier_mhz) or carrier_mhz <= 0):
        raise ValueError("Carrier MHz must be positive and finite")
    start = start.astimezone(timezone.utc)
    end = start + timedelta(hours=hours)

    ts = load.timescale(builtin=True)
    satellite = EarthSatellite.from_omm(ts, omm)
    site = wgs84.latlon(station.latitude_deg, station.longitude_deg,
                        elevation_m=station.elevation_m)
    relative = satellite - site
    events_t, events = satellite.find_events(
        site, ts.from_datetime(start), ts.from_datetime(end),
        altitude_degrees=station.min_elevation_deg)
    local_tz = ZoneInfo(station.timezone_name)
    epoch = satellite.epoch.utc_datetime().astimezone(timezone.utc)

    def point(t):
        alt, az, _ = relative.at(t).altaz()
        return float(alt.degrees), float(az.degrees) % 360

    def stamp(dt, tz):
        return dt.astimezone(tz).isoformat(timespec="seconds")

    result = []
    rise = peak = None
    for t, event in zip(events_t, events):
        if event == 0:
            rise, peak = t, None
        elif event == 1:
            if rise is not None:
                peak = t
        elif event == 2:
            if rise is None or peak is None:
                rise = peak = None
                continue
            aos = rise.utc_datetime().astimezone(timezone.utc)
            tca = peak.utc_datetime().astimezone(timezone.utc)
            los = t.utc_datetime().astimezone(timezone.utc)
            if not start <= aos < tca < los <= end:
                rise = peak = None
                continue
            _, a_az = point(rise)
            altitude, p_az = point(peak)
            _, l_az = point(t)
            shift = None
            if carrier_mhz is not None:
                position = relative.at(peak)
                xyz = position.position.km
                velocity = position.velocity.km_per_s
                radius = math.sqrt(sum(float(v)**2 for v in xyz))
                radial_km_s = sum(float(x)*float(v) for x, v in zip(xyz, velocity)) / radius
                # Approaching satellite -> negative range rate -> positive RX shift.
                shift = round(-carrier_mhz * 1_000_000 * radial_km_s / SPEED_OF_LIGHT_KM_S, 2)
            result.append(Pass(
                stamp(aos, timezone.utc), stamp(tca, timezone.utc), stamp(los, timezone.utc),
                stamp(aos, local_tz), stamp(tca, local_tz), stamp(los, local_tz),
                round(altitude, 3), round(a_az, 3), round(p_az, 3), round(l_az, 3),
                shift, stamp(epoch, timezone.utc),
                round((tca - epoch).total_seconds()/86400, 3)))
            rise = peak = None
    return result

def doppler_profile(omm: dict, station: Station, aos: datetime, tca: datetime,
                    los: datetime, carrier_mhz: float, step_seconds: int = 60) -> list[dict]:
    """Compute receive Doppler samples, including exact AOS, TCA and LOS.

    Uses geometric range rate (not an oscillator estimate or hardware command).
    AOS/LOS should be taken from the same pass prediction and station.
    """
    station.validate()
    if any(dt.tzinfo is None or dt.utcoffset() is None for dt in (aos, tca, los)):
        raise ValueError("AOS/TCA/LOS must be timezone-aware")
    aos, tca, los = (dt.astimezone(timezone.utc) for dt in (aos, tca, los))
    if not aos < tca < los:
        raise ValueError("Expected AOS < TCA < LOS")
    if not math.isfinite(carrier_mhz) or carrier_mhz <= 0:
        raise ValueError("Carrier MHz must be positive and finite")
    if not isinstance(step_seconds, int) or not 1 <= step_seconds <= 3600:
        raise ValueError("step_seconds must be 1..3600")
    if (los - aos).total_seconds() > 24 * 3600:
        raise ValueError("Doppler profile interval cannot exceed one day")

    ts = load.timescale(builtin=True)
    satellite = EarthSatellite.from_omm(ts, omm)
    observer = wgs84.latlon(station.latitude_deg, station.longitude_deg,
                            elevation_m=station.elevation_m)
    relative = satellite - observer
    points = {aos, tca, los}
    sample = aos + timedelta(seconds=step_seconds)
    while sample < los:
        points.add(sample)
        sample += timedelta(seconds=step_seconds)

    tz = ZoneInfo(station.timezone_name)
    result = []
    for timestamp in sorted(points):
        state = relative.at(ts.from_datetime(timestamp))
        altitude, azimuth, distance = state.altaz()
        # Radial range rate = dot(r, v) / |r|. This includes site rotation.
        xyz = state.position.km
        velocity = state.velocity.km_per_s
        range_km = float(distance.km)
        radial_km_s = sum(float(x) * float(v) for x, v in zip(xyz, velocity)) / range_km
        shift_hz = -carrier_mhz * 1_000_000 * radial_km_s / SPEED_OF_LIGHT_KM_S
        labels = []
        if timestamp == aos:
            labels.append("AOS")
        if timestamp == tca:
            labels.append("TCA")
        if timestamp == los:
            labels.append("LOS")
        result.append({
            "event": "/".join(labels) if labels else "sample",
            "time_utc": timestamp.isoformat(timespec="seconds"),
            "time_local": timestamp.astimezone(tz).isoformat(timespec="seconds"),
            "elevation_deg": round(float(altitude.degrees), 3),
            "azimuth_deg": round(float(azimuth.degrees) % 360, 3),
            "range_km": round(range_km, 3),
            "range_rate_km_s": round(radial_km_s, 5),
            "doppler_hz": round(shift_hz, 2),
            "received_frequency_mhz": round(carrier_mhz + shift_hz / 1e6, 9),
        })
    return result
