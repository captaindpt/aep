import unittest
import tempfile
import shutil
from pathlib import Path
import msgpack
import gzip
import time
from datetime import datetime, timezone

from aep.ledger import AEPLedger # Assuming 'aep' is in PYTHONPATH or installed

class TestAEPLedger(unittest.TestCase):

    def setUp(self):
        # Create a temporary directory for ledger files
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_aep_ledger_"))
        self.ledger_name = "unittest_log"

    def tearDown(self):
        # Remove the temporary directory after tests
        shutil.rmtree(self.test_dir)

    def _create_ledger(self, max_file_size_bytes: int = 1024) -> AEPLedger:
        return AEPLedger(
            ledger_base_path=self.test_dir,
            ledger_name=self.ledger_name,
            max_file_size_bytes=max_file_size_bytes
        )

    def test_01_initialization(self):
        ledger = self._create_ledger()
        self.assertEqual(ledger.ledger_base_path, self.test_dir)
        self.assertEqual(ledger.ledger_name, self.ledger_name)
        self.assertTrue(ledger.current_ledger_file.name.startswith(self.ledger_name))
        self.assertTrue(ledger.current_ledger_file.name.endswith(".aep.current"))
        self.assertTrue(self.test_dir.exists())

    def test_02_append_single_event(self):
        ledger = self._create_ledger()
        event_data = {"id": "event1", "ts": time.time(), "data": "test content"}
        ledger.append(event_data)
        
        self.assertTrue(ledger.current_ledger_file.exists())
        
        events_read = []
        with open(ledger.current_ledger_file, "rb") as f:
            unpacker = msgpack.Unpacker(f, raw=False)
            for event in unpacker:
                events_read.append(event)
        
        self.assertEqual(len(events_read), 1)
        self.assertEqual(events_read[0]["id"], "event1")
        self.assertEqual(events_read[0]["data"], "test content")

    def test_03_file_rotation(self):
        # Use a very small max_file_size_bytes to trigger rotation quickly
        ledger = self._create_ledger(max_file_size_bytes=50)
        
        event_data_large = {"id": "event_large", "ts": time.time(), "data": "A" * 100}
        event_data_small = {"id": "event_small", "ts": time.time(), "data": "B" * 10}

        # This should fill the first file and trigger rotation
        ledger.append(event_data_large) 
        time.sleep(0.01) # ensure different timestamp for archive file name
        # This should go into a new current file
        ledger.append(event_data_small)

        archived_files = list(self.test_dir.glob(f"{self.ledger_name}.aep.*.msgpack.gz"))
        self.assertEqual(len(archived_files), 1, "Should be one archived file")
        
        # Verify content of archived file (gzipped)
        archived_file_path = archived_files[0]
        events_from_archive = []
        with gzip.open(archived_file_path, "rb") as f:
            unpacker = msgpack.Unpacker(f, raw=False)
            for event in unpacker:
                events_from_archive.append(event)
        self.assertEqual(len(events_from_archive), 1)
        self.assertEqual(events_from_archive[0]["id"], "event_large")

        # Verify content of the new current file
        events_from_current = []
        if ledger.current_ledger_file.exists():
            with open(ledger.current_ledger_file, "rb") as f:
                unpacker = msgpack.Unpacker(f, raw=False)
                for event in unpacker:
                    events_from_current.append(event)
        self.assertEqual(len(events_from_current), 1)
        self.assertEqual(events_from_current[0]["id"], "event_small")

    def test_04_read_events_utility(self):
        ledger = self._create_ledger(max_file_size_bytes=50)
        event1 = {"id": "ev1", "data": "payload1" * 10} # ~70 bytes packed
        event2 = {"id": "ev2", "data": "payload2"}
        
        ledger.append(event1)
        time.sleep(0.01)
        ledger.append(event2)

        all_ledger_paths = ledger.get_all_ledger_files(include_current=True)
        self.assertGreaterEqual(len(all_ledger_paths), 2) # At least one archive and one current

        total_events_read = 0
        ids_read = set()
        for file_path in all_ledger_paths:
            events = ledger.read_events(file_path)
            for ev in events:
                ids_read.add(ev["id"])
            total_events_read += len(events)
        
        self.assertEqual(total_events_read, 2)
        self.assertIn("ev1", ids_read)
        self.assertIn("ev2", ids_read)

    def test_05_get_all_ledger_files(self):
        ledger = self._create_ledger(max_file_size_bytes=10)
        for i in range(3):
            ledger.append({"id": f"event_{i}", "data": "A"*5})
            time.sleep(0.01) # ensure distinct archive filenames
        
        # Should have 2 archived files and 1 current file
        all_files = ledger.get_all_ledger_files(include_current=True)
        self.assertEqual(len(all_files), 3, f"Files found: {[f.name for f in all_files]}")

        archived_files_only = ledger.get_all_ledger_files(include_current=False)
        self.assertEqual(len(archived_files_only), 2)
        for f_path in archived_files_only:
            self.assertTrue(f_path.name.endswith(".msgpack.gz"))

if __name__ == '__main__':
    unittest.main()
