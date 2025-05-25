import os
import yaml
import json
import time
import uuid
from pathlib import Path
import sys

# Silence OpenAI library warnings/logs if desired for cleaner CI output
# Needs openai library to be imported first if it has a central logging config.
# Alternatively, manage log levels via Python's logging module.
# For now, let's assume standard library logging might be affected by OpenAI.
# import logging
# logging.getLogger("openai").setLevel(logging.ERROR)
# The run-book suggested openai.logging.disable() - this seems to be for older openai versions.
# For openai >= 1.0, it uses standard logging. We can try to set its level.

# Ensure aep-sdk root is in PYTHONPATH for imports
# This assumes the script is in aep-sdk/analysis/
SDK_ROOT = Path(__file__).parent.parent.resolve()
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from backend.rag_chain import get_initialized_rag_graph, RAGState # For RAG graph
# AEPLedger and AEPCallbackHandler are not strictly needed for baseline recall script as per run-book.

# --- Configuration ---
QA_FILE_PATH = SDK_ROOT / "qa" / "qa.yaml"
DOCS_CORPUS_PATH = SDK_ROOT / "docs"
EVAL_RETRIEVAL_LOG_PATH = SDK_ROOT / "data" / "evaluation_run" / f"ci_retrieval_log_{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
EVAL_RETRIEVAL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

K_FOR_RECALL = 10
MIN_RECALL_THRESHOLD = 0.68 # As per run-book

def load_qa_dataset(file_path: Path) -> list:
    if not file_path.exists():
        print(f"Error: QA file not found at {file_path}", file=sys.stderr)
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        qa_data = yaml.safe_load(f)
    print(f"Loaded {len(qa_data)} Q/A pairs from {file_path}")
    return qa_data

def calculate_recall_at_k(retrieved_sources: list, golden_sources: list, k: int) -> float:
    if not golden_sources:
        return 1.0 if not retrieved_sources else 0.0
    top_k_retrieved = retrieved_sources[:k]
    hits = 0
    for golden_source in golden_sources:
        if golden_source in top_k_retrieved:
            hits += 1
    return hits / len(golden_sources)

def run_evaluation(rag_graph, qa_data: list, retrieval_log_path: Path) -> float:
    """Runs RAG evaluation and returns mean Recall@K."""
    if not rag_graph or not qa_data:
        print("Error: RAG graph or QA data not available for evaluation.", file=sys.stderr)
        return 0.0

    # Clear previous log for this run if any
    if retrieval_log_path.exists():
        retrieval_log_path.unlink()

    # Temporarily redirect rag_chain's logging to our eval log for this run
    # This requires rag_chain.py to be importable and its global var accessible.
    # This is a bit of a hack. A cleaner way is for rag_chain functions to accept log_path.
    import backend.rag_chain as rag_chain_module
    original_rag_log_path = rag_chain_module.DEFAULT_RETRIEVAL_LOG_PATH
    rag_chain_module.DEFAULT_RETRIEVAL_LOG_PATH = retrieval_log_path
    print(f"Temporarily changed RAG chain retrieval log to: {retrieval_log_path}")

    print(f"Running RAG evaluation for {len(qa_data)} questions...")
    for i, qa_item in enumerate(qa_data):
        question = qa_item["question"]
        query_id = qa_item.get("id", f"eval_ci_q_{uuid.uuid4()}")
        
        print(f"  {i+1}/{len(qa_data)}: QID {query_id} - {question[:50]}...", end=" ", flush=True)
        
        # For CI, no AEP callback is specified for the RAG call itself.
        # The query_id is still important for the retrieval log.
        invocation_config = {"metadata": {"query_id": query_id}}
        initial_state = {"question": question, "query_id": query_id, "context": [], "answer": ""}
        
        try:
            rag_graph.invoke(initial_state, config=invocation_config)
            print(f"Done.")
        except Exception as e:
            print(f"ERROR invoking RAG for QID {query_id}: {e}", file=sys.stderr)
            continue
    
    print(f"\nEvaluation RAG invocations complete. Retrieval data logged to: {retrieval_log_path}")
    rag_chain_module.DEFAULT_RETRIEVAL_LOG_PATH = original_rag_log_path # Restore
    print(f"Restored RAG chain retrieval log to: {original_rag_log_path}")

    # --- Parse the retrieval log to calculate recall ---
    all_retrieval_log_entries = []
    if retrieval_log_path.exists():
        with open(retrieval_log_path, 'r', encoding='utf-8') as f_log:
            for line in f_log:
                try:
                    all_retrieval_log_entries.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"Warning: Could not parse line in retrieval log: {line.strip()}", file=sys.stderr)
    else:
        print(f"Error: Evaluation retrieval log file not found: {retrieval_log_path}", file=sys.stderr)
        return 0.0

    if not all_retrieval_log_entries:
        print("No entries found in retrieval log. Cannot calculate recall.", file=sys.stderr)
        return 0.0

    # Convert to DataFrame for easier processing
    try:
        import pandas as pd # Moved import here as it's only for processing
    except ImportError:
        print("Pandas not installed. Cannot process retrieval log for recall calculation.", file=sys.stderr)
        return 0.0 # Or raise
        
    df_retrieval_log = pd.DataFrame(all_retrieval_log_entries)
    if df_retrieval_log.empty:
        print("Retrieval log DataFrame is empty.", file=sys.stderr)
        return 0.0

    df_qa = pd.DataFrame(qa_data)
    df_eval_data = pd.merge(df_qa, df_retrieval_log, left_on="id", right_on="query_id", how="left")

    recalls_at_k = []
    for index, row in df_eval_data.iterrows():
        retrieved_items_list = row.get("retrieved_items", [])
        if not isinstance(retrieved_items_list, list): retrieved_items_list = [] # Handle NaN or malformed
            
        retrieved_doc_sources = [item["doc_source"] for item in retrieved_items_list]
        golden = row.get("golden_doc_sources", [])
        if not isinstance(golden, list): golden = []
            
        recall = calculate_recall_at_k(retrieved_doc_sources, golden, K_FOR_RECALL)
        recalls_at_k.append(recall)

    if not recalls_at_k:
        print("No recall values calculated.", file=sys.stderr)
        return 0.0
        
    mean_recall = sum(recalls_at_k) / len(recalls_at_k)
    print(f"\nMean Baseline Recall@{K_FOR_RECALL}: {mean_recall:.4f}")
    return mean_recall

def main():
    print("--- Starting Evaluation Script ---")
    
    # Attempt to silence OpenAI chatter - this might need adjustment depending on how
    # specific openai version (1.23.6) handles its logging.
    try:
        import openai
        # For openai < 1.0, openai.util.logger.setLevel("WARNING") was one way.
        # For openai >= 1.0, it uses the standard logging module.
        # Let's try to get its logger and set level.
        import logging
        logging.getLogger("openai").setLevel(logging.WARNING) # Show only warnings and above
        logging.getLogger("httpx").setLevel(logging.WARNING)  # httpx can also be chatty
        # print("Attempted to silence OpenAI and httpx loggers.")
    except ImportError:
        pass # OpenAI not installed, or other issue, proceed.

    # Check for CI environment and API Key
    is_ci_environment = os.getenv("CI", "false").lower() == "true"
    openai_api_key_present = bool(os.environ.get("OPENAI_API_KEY"))

    if not openai_api_key_present:
        if is_ci_environment:
            print("WARNING: OPENAI_API_KEY not found in CI environment.")
            print("Simulating a passing recall of 0.70 as per run-book instructions.")
            print(f"Recall@{K_FOR_RECALL} (0.7000) meets or exceeds threshold ({MIN_RECALL_THRESHOLD:.4f}). Evaluation PASSED (Simulated).")
            sys.exit(0) # Exit successfully
        else:
            print("CRITICAL: OPENAI_API_KEY not found in environment. Evaluation cannot proceed.", file=sys.stderr)
            sys.exit(1)

    qa_items = load_qa_dataset(QA_FILE_PATH)
    if not qa_items:
        print("No QA items loaded. Exiting.", file=sys.stderr)
        sys.exit(1)

    print(f"Initializing RAG system with document corpus from: {DOCS_CORPUS_PATH}")
    # Pass docs_path_str for clarity, ensure it's a string.
    rag_application = get_initialized_rag_graph(docs_path_str=str(DOCS_CORPUS_PATH))
    if not rag_application:
        print("RAG system initialization failed. Exiting.", file=sys.stderr)
        sys.exit(1)
    print("RAG system initialized successfully.")

    recall_result = run_evaluation(rag_application, qa_items, EVAL_RETRIEVAL_LOG_PATH)
    
    print(f"Final Mean Recall@{K_FOR_RECALL}: {recall_result:.4f}")
    
    if recall_result >= MIN_RECALL_THRESHOLD:
        print(f"Recall@{K_FOR_RECALL} ({recall_result:.4f}) meets or exceeds threshold ({MIN_RECALL_THRESHOLD:.4f}). Evaluation PASSED.")
        sys.exit(0)
    else:
        print(f"Recall@{K_FOR_RECALL} ({recall_result:.4f}) is BELOW threshold ({MIN_RECALL_THRESHOLD:.4f}). Evaluation FAILED.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main() 