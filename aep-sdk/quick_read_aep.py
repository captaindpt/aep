import msgpack
import gzip
from pathlib import Path
import json
import sys

def read_aep_file(file_path_str: str):
    file_path = Path(file_path_str)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return []

    events = []
    print(f"Reading AEP events from: {file_path}")
    try:
        opener = gzip.open if file_path.suffix == ".gz" else open
        with opener(file_path, "rb") as f:
            # Set strict_map_key=False if keys might not always be strings (though they should be for JSON serializability)
            unpacker = msgpack.Unpacker(f, raw=False, strict_map_key=False) 
            for i, event in enumerate(unpacker):
                print(f"\n--- Event {i} (Trace ID: {event.get('trace_id', 'N/A')}, Type: {event.get('event_type', 'N/A')}, Source: {event.get('event_source', 'N/A')}) ---")
                # Pretty print the JSON
                try:
                    print(json.dumps(event, indent=2, default=str)) # Use default=str for non-serializable items like UUID
                except TypeError as te:
                    print(f"Could not fully serialize event to JSON for printing: {te}")
                    print("Raw event (or parts of it):")
                    for k, v in event.items():
                        try:
                            print(f"  {k}: {json.dumps(v, indent=2, default=str)}")
                        except TypeError:
                            print(f"  {k}: <Could not serialize value of type {type(v).__name__}>")
                
                events.append(event)
                if i >= 49: # Print up to 50 events (0-49)
                    print("\nStopping after 50 events for brevity...")
                    break
    except EOFError:
        print("Reached end of MsgPack stream (possibly an empty or truncated file).")
    except msgpack.exceptions.UnpackException as e:
        print(f"Msgpack unpack error in {file_path}: {e}. This might indicate a corrupted file or incorrect format.", file=sys.stderr)
    except Exception as e:
        print(f"General error reading {file_path}: {e}", file=sys.stderr)
    
    if not events:
        print("No events were successfully read.")
    return events

if __name__ == "__main__":
    if len(sys.argv) > 1:
        ledger_file_to_read = sys.argv[1]
        print(f"Attempting to read AEP ledger file: {ledger_file_to_read}")
        read_aep_file(ledger_file_to_read)
    else:
        print("Please provide the path to an AEP ledger file as a command-line argument.")
        print("Example:")
        print("  python quick_read_aep.py /Users/manirashahmadi/ccode/aep/aep-sdk/data/aep_runs/YOUR_AEP_FILE.aep.current")
        # You can set a default here for easier testing if you prefer:
        # default_file = "/Users/manirashahmadi/ccode/aep/aep-sdk/data/aep_runs/aep_eval_trace_aep_eval_20250522-123416_5aee3ee8.aep.current"
        # print(f"\nOr, if you want to run with a default, edit the script and uncomment the default_file line, then run: python quick_read_aep.py")
        # if default_file and Path(default_file).exists():
        #     print(f"\n--- Reading default file: {default_file} ---")
        #     read_aep_file(default_file) 