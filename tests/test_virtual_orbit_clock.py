"""Native C++ unit tests for the radio-independent virtual orbit clock."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class VirtualOrbitClockTests(unittest.TestCase):
    def test_native_clock_state_transitions(self):
        compiler = shutil.which("g++")
        if compiler is None:
            self.skipTest("g++ not installed; ESP32 module can still be compiled by PlatformIO")
        source = Path(__file__).resolve().parents[1] / "firmware" / "virtual_clock"
        program = r'''
#include <cassert>
#include <stdint.h>
#include "VirtualOrbitClockCore.h"
int main() {
    VirtualOrbitClockCore clock;
    assert(!clock.isRunning());
    assert(clock.now(1234, 1000000) == 1234);
    assert(!clock.start(1000000, 1000));
    assert(!clock.prepare(-1));
    assert(clock.prepare(1790000000));
    assert(clock.isPrepared());
    assert(clock.now(1234, 3000000) == 1234); // prepare does not override time
    assert(!clock.start(1000000, 0));
    assert(!clock.start(1000000, 16001));
    assert(clock.start(1000000, 4000)); // 4x
    assert(clock.isRunning());
    assert(clock.now(1234, 1000000) == 1790000000);
    assert(clock.now(1234, 1250000) == 1790000001);
    assert(clock.now(1234, 2500000) == 1790000006);
    assert(clock.now(1234, 500000) == 1790000000);
    clock.stop();
    assert(!clock.isRunning());
    assert(!clock.isPrepared());
    assert(clock.now(5678, 5000000) == 5678);
    assert(clock.prepare(1790000001));
    assert(clock.start(7000000)); // normal 1x
    assert(clock.now(5678, 9000000) == 1790000003);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "main.cpp"
            exe = Path(tmp) / "clock-test"
            src.write_text(program, encoding="utf-8")
            subprocess.run([compiler, "-std=c++11", "-Wall", "-Wextra",
                            "-Werror", "-I", str(source), str(src), "-o",
                            str(exe)], check=True, capture_output=True, text=True)
            subprocess.run([str(exe)], check=True, capture_output=True, text=True)
