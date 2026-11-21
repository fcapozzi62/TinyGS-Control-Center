import tempfile
import unittest
from pathlib import Path
from tinygs_control_center.catalog import OrbitalCatalog
from tinygs_control_center.stations import Station, StationStore

class StationTests(unittest.TestCase):
    def test_persist_update(self):
        with tempfile.TemporaryDirectory() as temp:
            with OrbitalCatalog(Path(temp) / "db.sqlite") as catalog:
                store = StationStore(catalog.conn)
                store.save(Station("demo", 41.9, 12.5, 50, "Europe/Rome", 5))
                self.assertEqual(store.get("demo").elevation_m, 50)
                store.save(Station("demo", 41.9, 12.5, 60, "Europe/Rome", 5))
                self.assertEqual(len(store.list()), 1)
                self.assertEqual(store.get("demo").elevation_m, 60)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            Station("bad", 91, 0).validate()
        with self.assertRaises(ValueError):
            Station("bad", 41, 12, timezone_name="Invalid/Timezone").validate()
