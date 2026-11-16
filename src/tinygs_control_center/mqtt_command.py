"""Wait for the TinyGS binary application ACK for a live begine command.

A broker PUBACK does not prove the firmware handled the command. Subscribe
before publishing; only accept a non-retained ACK received after publishing.
The firmware reports a native uint16_t in two bytes (little endian on ESP32).
"""
from __future__ import annotations

import math
import ssl
import threading
import time
from pathlib import Path

from .mqtt_publisher import publish_message


def decode_begine_ack(payload: bytes) -> int:
    """Decode firmware uint16_t ACK; zero means command handler completed."""
    if not isinstance(payload, bytes) or len(payload) != 2:
        raise ValueError("TinyGS begine ACK must be exactly two binary bytes")
    return int.from_bytes(payload, byteorder="little", signed=False)


def publish_begine_and_wait(
    host: str, port: int, username: str, password: str,
    topic: str, payload: str, *, cafile: str | None = None,
    timeout_sec: float = 10.0,
) -> dict:
    """Send one begine and await application ACK (no radio hardware readback).

    A dedicated MQTT client subscribes before publish, making it possible to
    catch immediate receiver responses. Only one outstanding command to a
    station should exist at a time; TinyGS ACK has no transaction identifier.
    """
    if not topic.startswith("tinygs/") or not topic.endswith("/cmnd/begine"):
        raise ValueError("Expected a concrete TinyGS /cmnd/begine topic")
    if len(topic.split("/")) != 5:
        raise ValueError("Expected tinygs/<user>/<station>/cmnd/begine")
    # Reuse basic transport validation without publishing anything.
    if not isinstance(host, str) or not host or any(x.isspace() for x in host):
        raise ValueError("Invalid MQTT broker host")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Invalid MQTT broker port")
    if not username or not password:
        raise ValueError("MQTT authentication required")
    if not isinstance(payload, str) or not payload:
        raise ValueError("Nonempty begine payload required")
    if not isinstance(timeout_sec, (float, int)) or not math.isfinite(timeout_sec) or not 0 < timeout_sec <= 120:
        raise ValueError("Timeout must be finite in (0,120] seconds")
    if port == 8883 and not cafile:
        raise ValueError("Port 8883 requires --cafile")
    if cafile and not Path(cafile).expanduser().is_file():
        raise ValueError("TLS CA file not found")
    ack_topic = topic[:-len("/cmnd/begine")] + "/stat/begine"

    try:
        import paho.mqtt.client as mqtt
    except ImportError as exc:
        raise ValueError("paho-mqtt not installed") from exc

    state = {"failure": None, "subscribed": False, "armed": False,
             "ack": None, "invalid_ack": None}
    subscription_ready = threading.Event()
    ack_ready = threading.Event()
    connected = threading.Event()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         protocol=mqtt.MQTTv311)
    client.username_pw_set(username, password)
    if cafile:
        client.tls_set_context(ssl.create_default_context(
            cafile=str(Path(cafile).expanduser())))

    def on_connect(cl, _userdata, _flags, reason_code, _properties):
        if reason_code.is_failure:
            state["failure"] = f"MQTT connection refused: {reason_code}"
            connected.set()
            return
        connected.set()
        rc, mid = cl.subscribe(ack_topic, qos=1)
        if rc != mqtt.MQTT_ERR_SUCCESS:
            state["failure"] = f"MQTT subscription request failed: {rc}"
            subscription_ready.set()

    def on_subscribe(_cl, _userdata, _mid, reason_codes, _properties):
        if any(code.is_failure for code in reason_codes):
            state["failure"] = "MQTT broker rejected the ACK subscription"
        else:
            state["subscribed"] = True
        subscription_ready.set()

    def on_disconnect(_cl, _userdata, _flags, reason_code, _properties):
        if reason_code.is_failure:
            state["failure"] = f"MQTT disconnected: {reason_code}"
            connected.set()
            subscription_ready.set()
            ack_ready.set()

    def on_message(_cl, _userdata, msg):
        if msg.topic != ack_topic or msg.retain or not state["armed"]:
            return
        try:
            state["ack"] = decode_begine_ack(bytes(msg.payload))
        except ValueError:
            state["invalid_ack"] = bytes(msg.payload).hex()
        ack_ready.set()

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    started = False
    try:
        client.connect(host, port, keepalive=30)
        client.loop_start()
        started = True
        deadline = time.monotonic() + timeout_sec
        if not connected.wait(max(0.0, deadline - time.monotonic())):
            raise ValueError("MQTT connection timed out")
        if state["failure"]:
            raise ValueError(state["failure"])
        if not subscription_ready.wait(max(0.0, deadline - time.monotonic())):
            raise ValueError("Timed out waiting for ACK subscription")
        if state["failure"] or not state["subscribed"]:
            raise ValueError(state["failure"] or "ACK subscription failed")

        # Arm immediately before publish; unrelated concurrent commands to
        # the same station must be excluded by the caller.
        state["armed"] = True
        info = client.publish(topic, payload, qos=1, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise ValueError(f"MQTT publish failed: {info.rc}")
        info.wait_for_publish(timeout=max(0.0, deadline - time.monotonic()))
        if not info.is_published():
            raise ValueError("Timed out waiting for broker PUBACK")

        ack_ready.wait(max(0.0, deadline - time.monotonic()))
        code = state["ack"]
        if state["invalid_ack"] is not None:
            status = "invalid_ack"
        elif code is None:
            status = "disconnected" if state["failure"] else "timeout"
        elif code == 0:
            status = "accepted"
        else:
            status = "rejected"

        return {
            "published": True,
            "broker_ack": True,
            "receiver_ack": code is not None,
            "receiver_accepted": code == 0,
            "ack_status": status,
            "ack_code": code,
            "invalid_ack_hex": state["invalid_ack"],
            "topic": topic,
            "ack_topic": ack_topic,
            "payload_bytes": len(payload.encode("utf-8")),
            "qos": 1,
            "retain": False,
            "note": "Receiver ACK confirms begine handler completion, not physical RF verification.",
        }
    finally:
        if started:
            client.disconnect()
            client.loop_stop()
