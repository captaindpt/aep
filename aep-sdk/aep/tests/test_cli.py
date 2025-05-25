import unittest
from unittest.mock import patch, mock_open
import tempfile
import shutil
from pathlib import Path
import msgpack
import subprocess # To run CLI as a subprocess
import sys
import json

from aep.ledger import AEPLedger
# To test CLI, we might need to invoke it or call its handler functions directly.
# For direct handler calls, we'd need to mock argparse.Namespace.
# For invoking CLI, we need to ensure it's runnable.

# If aep.cli.main is the entry point:
from aep.cli import main as cli_main

class TestAepCLI(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_aep_cli_"))
        self.ledger_base = self.test_dir / ".aep_test_ledgers"
        self.ledger_base.mkdir(parents=True, exist_ok=True)

        # Create a dummy AEPLedger for generating test files
        self.test_file_ledger = AEPLedger(ledger_base_path=self.ledger_base, ledger_name="filegen")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _run_cli_cmd(self, args_list):
        """Helper to run the CLI command and capture output/errors."""
        # This runs the CLI as if called from the command line.
        # Requires the package to be installed or PYTHONPATH set up.
        # For unit tests, it might be better to call handler functions directly
        # with mocked args, but subprocess tests true CLI behavior.
        
        # Prepend path to executable or 'poetry run aep' if needed
        # For now, assume direct call to cli_main with sys.argv patching
        with patch.object(sys, 'argv', ['aep'] + args_list):
            with patch('sys.stdout') as mock_stdout, patch('sys.stderr') as mock_stderr:
                exit_code = 0
                try:
                    cli_main() # This calls sys.exit, so catch it or mock it
                except SystemExit as e:
                    exit_code = e.code if isinstance(e.code, int) else 1 # sys.exit(None) is 0
                return { 
                    "stdout": mock_stdout.write.call_args_list if mock_stdout.write.call_args else [], 
                    "stderr": mock_stderr.write.call_args_list if mock_stderr.write.call_args else [],
                    "exit_code": exit_code
                }

    def test_merge_deduplication(self):
        ledger_name1 = "logA"
        ledger_name2 = "logB"
        ledger1_path = self.ledger_base / f"{ledger_name1}.aep.current"
        ledger2_path = self.ledger_base / f"{ledger_name2}.aep.current"

        event1_ts1 = {"id": "event1", "ts": 100, "focus_ms": 10, "payload": {"data": "e1_f1"}}
        event_shared_ts2 = {"id": "shared_event", "ts": 200, "focus_ms": 20, "payload": {"data": "shared"}}
        event_shared_ts4 = {"id": "shared_event", "ts": 400, "focus_ms": 22, "payload": {"data": "shared_newer_in_f2"}} # Same ID, different data
        event3_ts3 = {"id": "event3", "ts": 300, "focus_ms": 30, "payload": {"data": "e3_f2"}}

        # Create ledger file 1
        with open(ledger1_path, "ab") as f1:
            msgpack.pack(event1_ts1, f1)
            msgpack.pack(event_shared_ts2, f1) # Older version of shared_event

        # Create ledger file 2
        with open(ledger2_path, "ab") as f2:
            msgpack.pack(event_shared_ts4, f2) # Newer version of shared_event (will be kept if merge keeps first seen by ID)
                                            # My current merge keeps first by ID, so older will be kept.
                                            # Run-book: "dedupe based on event id". Doesn't specify which to keep.
                                            # Let's assume for test: first encountered ID wins.
            msgpack.pack(event3_ts3, f2)

        output_merged_file = self.test_dir / "merged_output.aep.msgpack"
        
        cli_args = [
            "merge", 
            str(output_merged_file), 
            str(ledger1_path), 
            str(ledger2_path)
        ]
        result = self._run_cli_cmd(cli_args)
        self.assertEqual(result["exit_code"], 0, f"CLI merge failed: {result['stderr']}")

        # Verify merged output
        self.assertTrue(output_merged_file.exists())
        merged_events_read = []
        temp_reader_ledger = AEPLedger() # Use for its read_events method
        merged_events_read = temp_reader_ledger.read_events(output_merged_file)
        
        self.assertEqual(len(merged_events_read), 3, "Deduplication should result in 3 unique events")

        # Events should be sorted by timestamp
        self.assertEqual(merged_events_read[0]["id"], "event1")
        self.assertEqual(merged_events_read[1]["id"], "shared_event") 
        self.assertEqual(merged_events_read[1]["payload"]["data"], "shared") # From file1 (first seen)
        self.assertEqual(merged_events_read[2]["id"], "event3")

        # Verify sorted by timestamp
        self.assertTrue(all(merged_events_read[i]["ts"] <= merged_events_read[i+1]["ts"] 
                          for i in range(len(merged_events_read)-1)))

    # TODO: Add tests for 'inspect' and 'list' commands

if __name__ == '__main__':
    unittest.main() 