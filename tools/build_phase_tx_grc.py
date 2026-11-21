"""Create a separate phased-TX GNU Radio flowgraph from the proven .grc file.

Usage:
  python tools/build_phase_tx_grc.py ORIGINAL.grc NEW_PHASE.grc

Requires PyYAML (commonly included with GNU Radio Companion).
Original is read-only. This generates a *burst-window* prototype: it does not
yet establish byte-for-byte packet boundaries or synchronized hardware time.
"""
import argparse
from copy import deepcopy
from pathlib import Path

import yaml


def variable(name, value, y, comment):
    return {
        "name": name, "id": "variable",
        "parameters": {"comment": comment, "value": value},
        "states": {"bus_sink": False, "bus_source": False,
                   "bus_structure": None, "coordinate": [184, y],
                   "rotation": 0, "state": "enabled"},
    }


def transform(graph):
    result = deepcopy(graph)
    blocks = result["blocks"]
    connections = result["connections"]
    nodes = {b["name"]: b for b in blocks if isinstance(b, dict) and "name" in b}
    required = ("blocks_stream_mux_0", "blocks_rotator_cc_0",
                "analog_const_source_x_0", "digital_gfsk_mod_0")
    if not all(n in nodes for n in required):
        raise ValueError("Expected blocks are missing; refusing to change unknown flowgraph")
    if nodes["blocks_stream_mux_0"]["parameters"]["lengths"] != "(4368000,2400000)":
        raise ValueError("Input stream mux differs from validated baseline")
    if not any(c[:1] == ["blocks_rotator_cc_0"] and c[2] == "blocks_stream_mux_0"
               for c in connections):
        raise ValueError("Input wiring differs from validated baseline")
    result["options"]["parameters"].update(
        id="sx1278_fsk_test_phase_tx",
        title="SX1278 FSK - Phase TX (experimental)",
        description="Phased FSK TX using the validated RF chain; original remains untouched.",
    )
    blocks.extend([
        variable("phase_ms", "100", 164, "TX phase inside each period in milliseconds"),
        variable("period_ms", "3000", 236, "TX period, milliseconds"),
        variable("burst_ms", "1820", 308, "ON window, milliseconds; frame alignment unverified"),
        variable("rf_rate", "2400000", 380, "HackRF IQ sample rate"),
        variable("phase_samples", "max(1, round(phase_ms*rf_rate/1000))", 452,
                 "0 ms approximated as 1 sample because mux needs positive slot"),
        variable("burst_samples", "round(burst_ms*rf_rate/1000)", 524,
                 "Samples per ON window"),
        variable("gap_samples",
                 "round((period_ms-phase_ms-burst_ms)*rf_rate/1000)", 596,
                 "Samples in trailing OFF window; keep positive"),
    ])
    mux = nodes["blocks_stream_mux_0"]["parameters"]
    mux["num_inputs"] = "3"
    mux["lengths"] = "(phase_samples, burst_samples, gap_samples)"
    mux["comment"] = "OFF phase / ON waveform / OFF gap; verify one full frame per ON window."
    connections[:] = [c for c in connections if c[2] != "blocks_stream_mux_0"]
    connections.extend([
        ["analog_const_source_x_0", "0", "blocks_stream_mux_0", "0"],
        ["blocks_rotator_cc_0", "0", "blocks_stream_mux_0", "1"],
        ["analog_const_source_x_0", "0", "blocks_stream_mux_0", "2"],
    ])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("original", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.original.resolve() == args.output.resolve():
        parser.error("Output must not overwrite the working original")
    with args.original.open(encoding="utf-8") as f:
        input_graph = yaml.safe_load(f)
    output_graph = transform(input_graph)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump(
        output_graph, sort_keys=False, allow_unicode=True, width=160),
        encoding="utf-8")
    print(f"Created {args.output} (original unchanged)")


if __name__ == "__main__":
    main()
