#!/usr/bin/env python3
"""Preview or apply the orbit-only clock hook to a local tinyGS-fsk-fifo tree.

Default: show unified diff, no writes. --apply copies headers and modifies
ONLY Radio::tle() in tinyGS/src/Radio/Radio.cpp. Never flashes the receiver.
"""
from __future__ import annotations

import argparse
import difflib
from pathlib import Path
import re
import shutil


def patch_radio_text(original: str) -> str:
    marker = '#include "Radio.h"'
    if original.count(marker) != 1:
        raise ValueError("Expected exactly one Radio.h include")
    head = original.find("void Radio::tle()")
    tail = original.find("void Radio::setFlag()", head)
    if head < 0 or tail < 0:
        raise ValueError("Could not isolate Radio::tle() safely")
    before, body, after = original[:head], original[head:tail], original[tail:]
    new_body, n = re.subn(
        r"time_t\s+currenttime\s*=\s*time\(NULL\)\s*;",
        "time_t currenttime = VirtualOrbitClock::now();",
        body,
    )
    if n != 1:
        raise ValueError(f"Expected one orbital time(NULL) use, found {n}")
    return (before.replace(marker, marker + '\n#include "VirtualOrbitClock.h"', 1)
            + new_body + after)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("firmware_root", type=Path,
                        help="Root containing tinyGS/src/Radio/Radio.cpp")
    parser.add_argument("--apply", action="store_true",
                        help="Explicit opt-in: modify worktree with backups")
    args = parser.parse_args()
    radio_dir = args.firmware_root.expanduser().resolve() / "tinyGS/src/Radio"
    file = radio_dir / "Radio.cpp"
    if not file.is_file():
        parser.error(f"Radio.cpp not found: {file}")
    original = file.read_text(encoding="utf-8")
    modified = patch_radio_text(original)
    diff = difflib.unified_diff(original.splitlines(True),
                                modified.splitlines(True),
                                fromfile="a/tinyGS/src/Radio/Radio.cpp",
                                tofile="b/tinyGS/src/Radio/Radio.cpp")
    print("".join(diff))
    if not args.apply:
        print("PREVIEW ONLY: no files changed. Add --apply after reviewing.")
        return 0

    sources = [Path(__file__).with_name(name) for name in
               ("VirtualOrbitClockCore.h", "VirtualOrbitClock.h")]
    destination = [radio_dir / p.name for p in sources]
    backup = file.with_name("Radio.cpp.before-virtual-orbit-clock")
    for dest in destination + [backup]:
        if dest.exists():
            parser.error(f"Refusing to overwrite existing file: {dest}")
    shutil.copy2(file, backup)
    for source, dest in zip(sources, destination):
        shutil.copy2(source, dest)
    file.write_text(modified, encoding="utf-8")
    print("Applied. No build or firmware upload performed.")
    print(f"Original Radio.cpp backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
