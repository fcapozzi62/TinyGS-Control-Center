"""Controlled MQTT publisher for a local broker.

This module is intentionally separate from the read-only monitor. Only
explicit callers can publish, never through preview or validation effects.
"""
from __future__ import annotations

import json
import math
import ssl
import time
from pathlib import Path


def publish_message(host: str, port: int, username: str, password: str,
                    topic: str, payload: str, *, cafile: str | None = None,
                    timeout_sec: float = 10.0) -> dict:
    """Publish one non-retained QoS 1 message; confirm broker PUBACK only.

    This does NOT confirm that the target receiver applied the command.
    """
    if not host or any(ch.isspace() for ch in host):
        raise ValueError("Invalid broker host")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Invalid broker port")
    if not username or not password:
        raise ValueError("MQTT credentials required")
    if not isinstance(topic, str) or not topic or any(
        segment in ("", "+", "#") for segment in topic.split("/")
    ) or any(ch in topic for ch in ("\x00", "+", "#")):
        raise ValueError("Publishing requires a concrete MQTT topic")
    if not isinstance(payload, str) or not payload:
        raise ValueError("Payload must be nonempty text")
    if not math.isfinite(timeout_sec) or not 0 < timeout_sec <= 120:
        raise ValueError("Timeout must be 0..120 seconds")
    if port == 8883 and not cafile:
        raise ValueError("Port 8883 requires --cafile")
    if cafile is not None and not Path(cafile).expanduser().is_file():
        raise ValueError("TLS CA file not found")

    try:
        import paho.mqtt.client as mqtt
    except ImportError as exc:
        raise ValueError("paho-mqtt not installed") from exc

    state = {"connected": False, "failed": None}
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
    client.username_pw_set(username, password)
    if cafile:
        client.tls_set_context(ssl.create_default_context(cafile=str(
            Path(cafile).expanduser())))

    def on_connect(_client, _userdata, _flags, reason_code, _properties):
        if reason_code.is_failure:
            state["failed"] = f"MQTT connect rejected: {reason_code}"
        else:
            state["connected"] = True

    def on_disconnect(_client, _userdata, _flags, reason_code, _properties):
        if not reason_code.is_failure:
            return
        state["failed"] = f"MQTT disconnected: {reason_code}"

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    started = False
    try:
        client.connect(host, port, keepalive=30)
        client.loop_start()
        started = True
        deadline = time.monotonic() + timeout_sec
        while not state["connected"]:
            if state["failed"]:
                raise ValueError(state["failed"])
            if time.monotonic() >= deadline:
                raise ValueError("MQTT connection timed out")
            time.sleep(0.02)
        info = client.publish(topic, payload=payload, qos=1, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise ValueError(f"MQTT publish failed: {info.rc}")
        remaining = max(0.0, deadline - time.monotonic())
        info.wait_for_publish(timeout=remaining)
        if not info.is_published():
            raise ValueError("Timed out waiting for MQTT PUBACK")
        return {
            "published": True,
            "broker_ack": True,
            "receiver_ack": False,
            "topic": topic,
            "payload_bytes": len(payload.encode("utf-8")),
            "qos": 1,
            "retain": False,
            "note": "PUBACK confirms broker receipt, not radio configuration.",
        }
    finally:
        if started:
            client.disconnect()
            client.loop_stop()
