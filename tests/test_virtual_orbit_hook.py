"""Patch script must isolate P13 call and never touch other time calls."""
import importlib.util
from pathlib import Path
import unittest


def load_script():
    path = Path(__file__).resolve().parents[1] / "firmware" / "virtual_clock" / "apply_orbit_clock.py"
    spec = importlib.util.spec_from_file_location("tcc_apply_orbit_clock", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class VirtualOrbitHookTests(unittest.TestCase):
    def test_only_orbit_time_is_replaced(self):
        original = (
            '#include "Radio.h"\n'
            'void Radio::tle() {\n'
            '  time_t currenttime =\n'
            '      time(NULL); // original comment\n'
            '}\n'
            'void Radio::setFlag() { time_t other = time(NULL); }\n'
        )
        modified = load_script().patch_radio_text(original)
        self.assertIn('#include "VirtualOrbitClock.h"', modified)
        self.assertIn('time_t currenttime = VirtualOrbitClock::now();', modified)
        self.assertIn('time_t other = time(NULL);', modified)
        self.assertEqual(modified.count('VirtualOrbitClock::now()'), 1)

    def test_reject_missing_or_ambiguous_hook(self):
        for text in (
            '#include "Radio.h"\nvoid Radio::tle() {}\nvoid Radio::setFlag() {}',
            '#include "Radio.h"\nvoid Radio::tle() {'
            ' time_t currenttime = time(NULL); time_t currenttime = time(NULL);'
            '}\nvoid Radio::setFlag() {}',
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                load_script().patch_radio_text(text)
