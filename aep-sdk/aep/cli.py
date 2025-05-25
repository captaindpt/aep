import argparse
import json # For pretty printing dictionaries
from pathlib import Path
import sys
import gzip # For writing merged gzipped output
import msgpack # For packing merged events

from .ledger import AEPLedger, DEFAULT_AEP_DIR, DEFAULT_LEDGER_NAME

def print_event(event, as_json=False):
    if as_json:
        print(json.dumps(event, indent=2, default=str))
    else:
        print(f"- Event ID: {event.get('id')}")
        print(f"  Timestamp: {event.get('ts')}")
        print(f"  Focus (ms): {event.get('focus_ms')}")
        print(f"  Kind: {event.get('focus_kind')}")
        if "query_id" in event:
            print(f"  Query ID: {event.get('query_id')}")
        if "session_id" in event: # For human_dwell events
            print(f"  Session ID: {event.get('session_id')}")
        payload = event.get("payload", {})
        print(f"  Payload: ")
        for key, value in payload.items():
            if isinstance(value, str) and len(value) > 100:
                value_display = value[:100] + "..."
            else:
                value_display = value
            print(f"    {key}: {value_display}")
        print("---")

def handle_inspect(args):
    ledger_base = Path(args.ledger_base_path).resolve()
    ledger = AEPLedger(ledger_base_path=ledger_base, ledger_name=args.ledger_name)
    print(f"Inspecting ledger: '{args.ledger_name}' in directory: {ledger_base}")
    files_to_inspect = []
    if args.file:
        file_to_inspect = Path(args.file)
        if not file_to_inspect.is_absolute():
             file_to_inspect = ledger_base / file_to_inspect
        if not file_to_inspect.exists():
            print(f"Error: Specified file does not exist: {file_to_inspect}", file=sys.stderr)
            return 1
        files_to_inspect.append(file_to_inspect)
        print(f"Targeting specific file: {file_to_inspect}")
    else:
        files_to_inspect = ledger.get_all_ledger_files(include_current=not args.archived_only)
        if args.current_only:
            if ledger.current_ledger_file.exists():
                files_to_inspect = [ledger.current_ledger_file]
            else:
                files_to_inspect = []
        if not files_to_inspect:
            print("No ledger files found to inspect.")
            return 0
        print(f"Found {len(files_to_inspect)} file(s) to inspect:")
        for f_path in files_to_inspect:
            print(f"  - {f_path.name} (Size: {f_path.stat().st_size} bytes)")
    total_events_inspected = 0
    for file_path in files_to_inspect:
        print(f"\n--- Events from: {file_path.name} ---")
        events = ledger.read_events(file_path)
        if not events:
            print("(No events in this file or file is empty/corrupted)")
            continue
        for i, event in enumerate(events):
            if args.limit is not None and total_events_inspected >= args.limit:
                print(f"Reached inspection limit of {args.limit} events.")
                return 0
            print_event(event, as_json=args.json)
            total_events_inspected += 1
        if not args.json:
             print(f"(Found {len(events)} events in {file_path.name})")
    print(f"\nTotal events inspected across all targeted files: {total_events_inspected}")
    return 0

def handle_list_ledgers(args):
    ledger_base = Path(args.ledger_base_path).resolve()
    ledger = AEPLedger(ledger_base_path=ledger_base, ledger_name=args.ledger_name)
    print(f"Listing files for ledger: '{args.ledger_name}' in directory: {ledger_base}")
    ledger_files = ledger.get_all_ledger_files(include_current=True)
    if not ledger_files:
        print("No ledger files found.")
        return 0
    for f_path in ledger_files:
        status = " (current)" if f_path == ledger.current_ledger_file else " (archived)"
        print(f"  - {f_path.name}{status} (Size: {f_path.stat().st_size} bytes)")
    return 0

def handle_merge(args):
    output_file = Path(args.output_file).resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    all_events = []
    seen_event_ids = set()
    
    # Ledger instance for reading (doesn't matter which ledger_name, uses its read_events utility)
    # Or we can make read_events a staticmethod or free function if it doesn't need ledger state.
    # Current AEPLedger.read_events is an instance method but doesn't use self beyond printing.
    # For simplicity, create a dummy ledger to use its read_events method.
    # A cleaner way would be a static method on AEPLedger or a separate utility function.
    temp_ledger_reader = AEPLedger() 

    print(f"Merging ledger files into: {output_file}")
    input_file_paths = [Path(f).resolve() for f in args.input_files]

    for file_path in input_file_paths:
        if not file_path.exists():
            print(f"Warning: Input file not found, skipping: {file_path}", file=sys.stderr)
            continue
        print(f"Reading events from: {file_path.name}...")
        events = temp_ledger_reader.read_events(file_path)
        count_before_dedupe = len(events)
        new_events_from_file = 0
        for event in events:
            event_id = event.get("id")
            if event_id and event_id not in seen_event_ids:
                all_events.append(event)
                seen_event_ids.add(event_id)
                new_events_from_file +=1
            elif not event_id:
                # Event has no ID, append it but warn
                print(f"Warning: Event found without an ID in {file_path.name}, appending as is.")
                all_events.append(event)
                new_events_from_file += 1 
        print(f"  Read {count_before_dedupe} events, added {new_events_from_file} new unique events.")

    if not all_events:
        print("No events found in input files. Output file will be empty.")
        # Create an empty file or do nothing? Let's create an empty one if specified.
        open(output_file, 'wb').close() # Create empty file if writing binary
        return 0

    # Sort events by timestamp
    all_events.sort(key=lambda x: x.get("ts", 0)) # Default to 0 if ts is missing, for sort stability
    print(f"Total unique events to write: {len(all_events)}")

    # Write to output file (gzipped msgpack)
    try:
        # Determine if output should be gzipped based on extension
        use_gzip = output_file.name.endswith(".gz")
        
        open_func = gzip.open if use_gzip else open
        mode = "wb"

        with open_func(output_file, mode) as f_out:
            for event in all_events:
                msgpack.pack(event, f_out)
        print(f"Successfully merged {len(all_events)} events to {output_file}")
    except Exception as e:
        print(f"Error writing merged output to {output_file}: {e}", file=sys.stderr)
        return 1
    return 0

def main():
    parser = argparse.ArgumentParser(description="AEP SDK Command Line Interface.")
    parser.add_argument(
        "--ledger-base-path", 
        default=str(DEFAULT_AEP_DIR),
        help=f"Base directory for AEP ledger files. Default: {DEFAULT_AEP_DIR}"
    )
    parser.add_argument(
        "--ledger-name", 
        default=DEFAULT_LEDGER_NAME,
        help=f"Name of the ledger to operate on. Default: {DEFAULT_LEDGER_NAME}"
    )

    subparsers = parser.add_subparsers(dest="command", required=True, help="Sub-command to execute")

    # --- Inspect command ---
    inspect_parser = subparsers.add_parser("inspect", help="Inspect events in ledger files.")
    inspect_parser.add_argument(
        "--file", 
        type=str, 
        default=None, 
        help="Specific ledger file to inspect (name or path relative to ledger base). If not set, inspects all relevant files."
    )
    inspect_parser.add_argument(
        "--current-only", 
        action="store_true", 
        help="Only inspect the current, active ledger file."
    )
    inspect_parser.add_argument(
        "--archived-only", 
        action="store_true", 
        help="Only inspect archived (gzipped) ledger files."
    )
    inspect_parser.add_argument(
        "-n", "--limit", 
        type=int, 
        default=None, 
        help="Limit the number of events to inspect."
    )
    inspect_parser.add_argument(
        "--json", 
        action="store_true", 
        help="Output events in JSON format."
    )
    inspect_parser.set_defaults(func=handle_inspect)

    # --- List command (simple alias/alternative to inspect for just listing files) ---
    list_parser = subparsers.add_parser("list", help="List ledger files.")
    list_parser.set_defaults(func=handle_list_ledgers)
    
    # --- Merge command (New) ---
    merge_parser = subparsers.add_parser("merge", help="Merge multiple ledger files into a single output file.")
    merge_parser.add_argument(
        "output_file", 
        help="Path to the merged output ledger file (e.g., merged.aep.msgpack or merged.aep.msgpack.gz for compression)."
    )
    merge_parser.add_argument(
        "input_files", 
        nargs='+', 
        help="Paths to input ledger files (current or .gz archives)."
    )
    merge_parser.set_defaults(func=handle_merge)

    # --- Upload command (placeholder) ---
    # upload_parser = subparsers.add_parser("upload", help="Upload ledger files to a telemetry endpoint.")
    # upload_parser.add_argument("--endpoint", default="<default_upload_url>")
    # upload_parser.add_argument("files", nargs='*', help="Specific files to upload. If empty, uploads based on config or all.")
    # upload_parser.set_defaults(func=handle_upload) # To be implemented

    args = parser.parse_args()
    
    if hasattr(args, 'func'):
        sys.exit(args.func(args))
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main() 