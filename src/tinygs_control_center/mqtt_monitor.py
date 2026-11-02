"""Read-only MQTT telemetry monitor for TinyGS Control Center.

This module never calls publish(). Use it first against a local test broker.
"""
from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime, timezone

from .telemetry import StationRegistry


def validate_monitor_settings(host: str, port: int, topic: str,
                              timeout_sec: float, max_messages: int) -> None:
    if not isinstance(host, str) or not host or any(c.isspace() for c in host):
        raise ValueError("MQTT host must be a nonempty hostname or IP address")
    if not isinstance(port, int) or not (1 <= port <= 65535):
        raise ValueError("MQTT port must be in 1..65535")
    if not isinstance(topic, str) or not topic or "\x00" in topic:
        raise ValueError("MQTT subscription filter must be nonempty and contain no NUL")
    segments = topic.split("/")
    for i, segment in enumerate(segments):
        if "#" in segment and (segment != "#" or i != len(segments) - 1):
            raise ValueError("MQTT '#' wildcard must occupy the last segment")
        if "+" in segment and segment != "+":
            raise ValueError("MQTT '+' wildcard must occupy an entire segment")
    if not isinstance(timeout_sec, (int, float)) or not math.isfinite(timeout_sec) or timeout_sec <= 0:
        raise ValueError("timeout_sec must be finite and positive")
    if type(max_messages) is not int or max_messages < 0:
        raise ValueError("max_messages must be >= 0")


def format_message(topic: str, payload: bytes, qos: int, retain: bool) -> dict:
    """Represent binary packets safely without losing any bytes."""
    try:
        body = payload.decode("utf-8")
    except UnicodeDecodeError:
        body = None
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "topic": topic,
        "qos": qos,
        "retain": retain,
        "payload_size": len(payload),
    }
    if body is None:
        result["payload_hex"] = payload.hex()
        result["encoding"] = "hex"
    else:
        result["payload"] = body
        result["encoding"] = "utf-8"
    return result


def process_monitor_message(message, registry: StationRegistry | None = None) -> dict:
    """Render one received MQTT message and optionally update station state.

    Unsupported topics do not create stations. This function never publishes.
    """
    result = format_message(message.topic, message.payload,
                            message.qos, message.retain)
    if registry is not None:
        registry.ingest(message.topic, message.payload)
    return result


def station_summary(registry: StationRegistry) -> dict:
    """Snapshot observed stations without claiming online presence."""
    return {"type": "station_summary", "stations": registry.snapshots()}


def monitor(host: str, port: int, username: str, password: str,
            topic: str = "tinygs/#", timeout_sec: float = 30,
            max_messages: int = 0,
            summarize_stations: bool = False) -> int:
    """Connect and subscribe; never transmit application MQTT messages.

    max_messages=0 continues until timeout or Ctrl-C. Password only enters
    through the caller's environment and is never logged.
    """
    validate_monitor_settings(host, port, topic, timeout_sec, max_messages)
    if not username or not password:
        raise ValueError("MQTT username and password are required")
    try:
        import paho.mqtt.client as mqtt
    except ImportError as exc:
        raise ValueError("paho-mqtt not installed: run python -m pip install -e .") from exc

    state = {"connected": False, "count": 0, "failed": None}
    registry = StationRegistry() if summarize_stations else None
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id="tcc-monitor", protocol=mqtt.MQTTv311)
    client.username_pw_set(username, password)

    def on_connect(_client, _userdata, _flags, reason_code, _properties):
        if reason_code.is_failure:
            state["failed"] = f"MQTT connection refused: {reason_code}"
            return
        state["connected"] = True
        rc, _mid = _client.subscribe(topic, qos=0)
        if rc != mqtt.MQTT_ERR_SUCCESS:
            state["failed"] = f"MQTT subscribe failed: {rc}"

    def on_subscribe(_client, _userdata, _mid, reason_codes, _properties):
        if any(code.is_failure for code in reason_codes):
            state["failed"] = "MQTT broker rejected subscription"

    def on_message(_client, _userdata, message):
        print(json.dumps(process_monitor_message(message, registry),
                         ensure_ascii=False), flush=True)
        state["count"] += 1

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    print(f"Monitoring {host}:{port}, topic={topic!r}; read-only, timeout={timeout_sec}s",
          file=sys.stderr, flush=True)
    try:
        client.connect(host, port, keepalive=30)
        client.loop_start()
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if state["failed"]:
                raise ValueError(state["failed"])
            if max_messages and state["count"] >= max_messages:
                return 0
            time.sleep(0.1)
        if not state["connected"]:
            raise ValueError("MQTT connect timed out")
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        client.disconnect()
        client.loop_stop()
        if registry is not None:
            print(json.dumps(station_summary(registry),
                             ensure_ascii=False), flush=True)
