import msgpack
import gzip
import os
from pathlib import Path
import time
from datetime import datetime, timezone
from typing import Any, Dict, Union, Optional, List
import portalocker
import sys

DEFAULT_AEP_DIR = Path.home() / ".aep"
DEFAULT_LEDGER_NAME = "default"
DEFAULT_MAX_FILE_SIZE_BYTES = 1 * 1024 * 1024  # 1MB

class AEPLedger:
    """
    Handles writing AEP events to a rotating, gzipped MsgPack ledger.
    """

    def __init__(
        self,
        ledger_base_path: Union[str, Path] = DEFAULT_AEP_DIR,
        ledger_name: str = DEFAULT_LEDGER_NAME,
        max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    ):
        """
        Initializes the AEPLedger.

        Args:
            ledger_base_path: Directory where ledger files will be stored.
                              Defaults to ~/.aep/.
            ledger_name: Base name for the ledger files (e.g., 'default', 'my_app').
                         Defaults to 'default'.
            max_file_size_bytes: Maximum size for an active ledger file before rotation.
                                 Defaults to 1MB.
        """
        self.ledger_base_path = Path(ledger_base_path)
        self.ledger_name = ledger_name
        self.max_file_size_bytes = max_file_size_bytes

        self.ledger_base_path.mkdir(parents=True, exist_ok=True)
        self.current_ledger_file = self.ledger_base_path / f"{self.ledger_name}.aep.current"

    def _rotate_if_needed(self) -> None:
        """
        Checks if the current ledger file exceeds the maximum size and rotates it.
        """
        if not self.current_ledger_file.exists():
            return

        current_size = self.current_ledger_file.stat().st_size
        if current_size >= self.max_file_size_bytes:
            timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            archive_file_name = f"{self.ledger_name}.aep.{timestamp_str}.msgpack.gz"
            archive_file_path = self.ledger_base_path / archive_file_name

            try:
                with open(self.current_ledger_file, "rb") as f_in, gzip.open(archive_file_path, "wb") as f_out:
                    f_out.write(f_in.read())
                
                # Remove the old current file after successful gzipping
                self.current_ledger_file.unlink()
            except Exception as e:
                # Handle errors during rotation, e.g., log them.
                # For now, print to stderr. A more robust app might use logging.
                print(f"Error during ledger rotation: {e}")
                # Avoid deleting current_ledger_file if archiving failed to prevent data loss.
                # The file will be re-checked and re-tried on next append.
                return

    def append(self, event: Dict[str, Any]) -> None:
        """
        Appends a single AEP event to the current ledger file.
        Rotates the ledger if it exceeds the configured size.
        Uses file locking to prevent corruption from multiple writers.

        Args:
            event: The AEP event dictionary to append.
        """
        # Rotate must happen *before* acquiring the lock on current_ledger_file,
        # especially if rotation renames/deletes current_ledger_file.
        # However, _rotate_if_needed itself reads stat() and then renames/gzips.
        # This means rotation itself needs to be atomic or careful about the current file.
        # For now, let's assume _rotate_if_needed is quick and issues are rare.
        # A more robust rotation might lock a meta-file or use a temporary name for new current.
        self._rotate_if_needed() 
        
        try:
            # Lock the current ledger file for append operations.
            # Using "ab" mode implies we want to append if it exists, or create if not.
            # portalocker.Lock expects the file to exist for some lock types on some OS,
            # but "ab" mode within the with statement should handle creation.
            with portalocker.Lock(self.current_ledger_file, "ab", timeout=5) as f: # Increased timeout
                msgpack.pack(event, f)
                f.flush() # Ensure data is written to OS buffers
                os.fsync(f.fileno()) # Ensure data is written to disk. TODO: For high-volume, consider batching/async writes.
        except portalocker.exceptions.LockException as le:
            print(f"Error acquiring lock for {self.current_ledger_file}: {le}", file=sys.stderr)
            # Optionally, implement a retry mechanism or specific error handling
        except Exception as e:
            print(f"Error appending to ledger {self.current_ledger_file}: {e}", file=sys.stderr)

    def read_events(self, file_path: Path) -> List[Dict[str, Any]]:
        """Reads all MsgPack events from a given ledger file (gzipped or plain)."""
        events = []
        try:
            if file_path.suffix == ".gz":
                with gzip.open(file_path, "rb") as f:
                    unpacker = msgpack.Unpacker(f, raw=False)
                    for event in unpacker:
                        events.append(event)
            else:
                with open(file_path, "rb") as f:
                    unpacker = msgpack.Unpacker(f, raw=False)
                    for event in unpacker:
                        events.append(event)
        except FileNotFoundError:
            print(f"Ledger file not found: {file_path}")
        except Exception as e:
            print(f"Error reading ledger file {file_path}: {e}")
        return events

    def get_all_ledger_files(self, include_current: bool = True) -> List[Path]:
        """Gets a list of all ledger files (archived and optionally current)."""
        archived_files = sorted(self.ledger_base_path.glob(f"{self.ledger_name}.aep.*.msgpack.gz"))
        all_files = list(archived_files)
        if include_current and self.current_ledger_file.exists():
            all_files.append(self.current_ledger_file)
        return all_files

    def __repr__(self) -> str:
        return (
            f"AEPLedger(ledger_base_path='{self.ledger_base_path}', "
            f"ledger_name='{self.ledger_name}', "
            f"current_file='{self.current_ledger_file}')"
        )

# Example Usage (can be moved to a test or CLI later)
if __name__ == "__main__":
    print("Testing AEPLedger...")
    # Use a temporary directory for testing to avoid cluttering ~/.aep
    test_ledger_dir = Path("./test_aep_ledger_data")
    test_ledger_dir.mkdir(parents=True, exist_ok=True)

    # Create a ledger with a small max size for testing rotation
    ledger = AEPLedger(
        ledger_base_path=test_ledger_dir,
        ledger_name="test_log",
        max_file_size_bytes=1000  # 1KB for quick rotation
    )
    print(ledger)

    print(f"Writing events to: {ledger.current_ledger_file}")
    for i in range(20):
        event_data = {
            "id": f"event_{i}",
            "ts": time.time(),
            "focus_ms": 100 + i * 10,
            "payload": {"data": f"Sample payload content {i}" * 10}, # Make payload larger
            "focus_kind": "test_event"
        }
        ledger.append(event_data)
        print(f"Appended event {i}, current file size: {ledger.current_ledger_file.stat().st_size if ledger.current_ledger_file.exists() else 0} bytes")
        time.sleep(0.01) # Ensure unique timestamps for archive files if rotation is very fast

    print("\nAll ledger files after writing:")
    for lf_path in ledger.get_all_ledger_files():
        print(f" - {lf_path.name} (Size: {lf_path.stat().st_size} bytes)")

    print("\nReading events from all files:")
    total_events_read = 0
    for lf_path in ledger.get_all_ledger_files():
        print(f"Reading from {lf_path.name}...")
        events = ledger.read_events(lf_path)
        total_events_read += len(events)
        # for event in events:
        #     print(f"  {event['id']}")
    print(f"Total events read from all files: {total_events_read}")

    # Cleanup test directory
    # import shutil
    # shutil.rmtree(test_ledger_dir)
    # print(f"Cleaned up {test_ledger_dir}") 