# AEP SDK Evaluation Notebook Content

This notebook evaluates the RAG system, focusing on Recall@K with and without AEP-based re-ranking.

## 1. Setup and Configuration

Import necessary libraries, configure paths, and load API keys (ensure `OPENAI_API_KEY` is set in your environment).

```{code-cell} ipython3
import os
import yaml
import json
import time
import uuid
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Assuming the SDK is installed or PYTHONPATH is set up to find 'aep' and 'backend'
# For direct notebook execution if SDK not installed, adjust sys.path:
import sys
# Add aep-sdk root to sys.path to find `aep` and `backend` modules
# This assumes the notebook is in aep-sdk/analysis/
module_root = Path(_dh[0]).parent.parent # In Jupyter, _dh[0] is notebook dir
sys.path.insert(0, str(module_root))

from backend.rag_chain import get_initialized_rag_graph, RAGState # For RAG graph
from aep.ledger import AEPLedger               # For potential ledger interaction
from aep.callback import AEPCallbackHandler    # For RAG AEP events

# --- Configuration ---
QA_FILE_PATH = module_root / "qa" / "qa.yaml"
# Path to the main document corpus, ensure this matches where your RAG chain loads from
DOCS_CORPUS_PATH = module_root / "docs"

# Ledger for RAG LLM events (same one used by the backend's RAG chain)
# This is for inspection or if tests here generate their own LLM events.
EVAL_RAG_LEDGER_NAME = "evaluation_rag_llm_events"
eval_rag_ledger = AEPLedger(ledger_name=EVAL_RAG_LEDGER_NAME)
aep_eval_callback_handler = AEPCallbackHandler(ledger=eval_rag_ledger)

# Retrieval log for this evaluation run
EVAL_RETRIEVAL_LOG_DIR = module_root / "data" / "evaluation_run"
EVAL_RETRIEVAL_LOG_DIR.mkdir(parents=True, exist_ok=True)
eval_retrieval_log_file = EVAL_RETRIEVAL_LOG_DIR / f"retrieval_log_{time.strftime('%Y%m%d-%H%M%S')}.jsonl"

# Ensure OpenAI API key is available
if not os.environ.get("OPENAI_API_KEY"):
    print("CRITICAL: OPENAI_API_KEY not found in environment. Evaluation will fail.")
    # Potentially raise an error or exit for critical missing config

print(f"SDK modules root: {module_root}")
print(f"QA file: {QA_FILE_PATH}")
print(f"Docs corpus: {DOCS_CORPUS_PATH}")
print(f"Eval RAG LLM event ledger: {eval_rag_ledger.current_ledger_file}")
print(f"Eval retrieval log: {eval_retrieval_log_file}")
```

## 2. Load QA Dataset

Load the 100 Q/A pairs from `qa/qa.yaml`.

```{code-cell} ipython3
def load_qa_dataset(file_path: Path) -> list:
    if not file_path.exists():
        print(f"Error: QA file not found at {file_path}")
        return []
    with open(file_path, 'r') as f:
        qa_data = yaml.safe_load(f)
    print(f"Loaded {len(qa_data)} Q/A pairs from {file_path}")
    return qa_data

qa_dataset = load_qa_dataset(QA_FILE_PATH)

# Display a sample
if qa_dataset:
    print("\nSample QA item:")
    print(json.dumps(qa_dataset[0], indent=2))
```

## 3. Initialize RAG System

Initialize the RAG graph from our backend. This will also load and index the documents from `aep-sdk/docs/`.

```{code-cell} ipython3
# Initialize the RAG graph (loads/indexes documents from DOCS_CORPUS_PATH)
# Pass the docs_path explicitly to ensure it uses the one defined for this eval.
print(f"\nInitializing RAG system with document corpus from: {DOCS_CORPUS_PATH}")
rag_app = get_initialized_rag_graph(docs_path_str=str(DOCS_CORPUS_PATH), force_reindex_docs=False) # Set force_reindex=True if docs changed

if rag_app:
    print("RAG system initialized successfully.")
else:
    print("Error: RAG system failed to initialize.")
    # Consider stopping the notebook if RAG init fails
```

## 4. Run Baseline Evaluation (Recall@K)

Iterate through the QA dataset, get baseline retrieved documents from the RAG system, and calculate Recall@K.

```{code-cell} ipython3
def get_baseline_retrieved_docs(question: str, query_id: str, rag_graph: RAGState, k_retrieval: int = 10) -> list:
    """
    Invokes the RAG graph up to the retrieval step and returns retrieved document sources.
    This function simulates getting just the retriever's output.
    It will call the full graph but we are interested in the context from the 'retrieve' step.
    A more direct way would be to expose the retriever component of the graph if possible,
    or reconstruct the retrieval logic here for pure baseline.

    For now, we'll use the 'retrieve_documents' node's logic by inspecting its state output,
    but we need to be careful as rag_chain.py's retrieve_documents also writes to a global log.
    Alternatively, we can call the full graph and then parse the intermediate retrieval_log.jsonl.

    Let's directly use the vector_store from rag_chain.py for pure baseline retrieval 
    to avoid full graph invocation for just retrieval, if vector_store is accessible.
    Accessing rag_chain.vector_store (global in that module) directly is a bit of a hack.
    A cleaner way would be for get_initialized_rag_graph to return the vector_store too.
    
    For this eval, we'll modify rag_chain.py to log retrieval for us when invoked.
    The RAG graph is already logging to DEFAULT_RETRIEVAL_LOG_PATH, which is great.
    We just need to ensure our eval queries use unique query_ids and we can parse that log.
    Or, we can run the retrieve node and capture its output if the graph structure allows.

    Let's simplify: assume `rag_chain.retrieve_documents` can be called or its logic replicated.
    The current `rag_chain.retrieve_documents` writes to DEFAULT_RETRIEVAL_LOG_PATH.
    We need to ensure this evaluation's retrieval is logged to our *eval_retrieval_log_file*.

    The `rag_chain.retrieve_documents` node is part of the graph. When the graph is invoked,
    this node is called. Its output (context) is available in the final state if the graph
    is structured to pass it through or if we can inspect intermediate states.
    The `rag_chain.retrieve_documents` also writes to a retrieval log. 
    We will configure our RAG graph invocation for *this evaluation script* to use a specific log if possible,
    or rely on filtering the main log by query_id.

    Re-thinking: The `retrieve_documents` node in `rag_chain.py` already logs to `DEFAULT_RETRIEVAL_LOG_PATH`.
    The most straightforward way is to run the full graph for each QA item, ensuring unique query_ids,
    and then parse `DEFAULT_RETRIEVAL_LOG_PATH` filtering by those query_ids to get retrieved items.
    The `get_initialized_rag_graph` function in `rag_chain.py` uses `DEFAULT_RETRIEVAL_LOG_PATH`.
    For this eval, we should probably make the log path configurable in `retrieve_documents` or have
    `get_initialized_rag_graph` set it up for our specific eval log path.
    Let's assume for now the RAG chain logs to `eval_retrieval_log_file` if configured.
    Modifying `rag_chain.py` to accept a retrieval_log_path is cleaner.
    
    If rag_chain.py is NOT modified, we run the graph and then parse the default log.
    Let's proceed with that and ensure unique query_ids for this run.
    """
    if not rag_graph:
        print("RAG graph not available.")
        return []

    # This invoke will use the aep_eval_callback_handler for LLM AEP events.
    # The retrieve_documents node within rag_graph will log to its configured retrieval log.
    # Ensure query_id is passed to the graph state and metadata
    invocation_config = {
        "callbacks": [aep_eval_callback_handler],
        "metadata": {"query_id": query_id}
    }
    initial_state = {"question": question, "query_id": query_id, "context": [], "answer": ""}
    
    # Invoking the full graph to ensure retrieval log is populated by the `retrieve_documents` node.
    final_state = rag_graph.invoke(initial_state, config=invocation_config)
    
    # Now, we need to get the retrieved documents. They are not directly in final_state["context"]
    # in a way that includes scores for baseline. The log file is the source of truth for retrieved items.
    # We need to read our specific eval_retrieval_log_file after all queries are run, or query by query_id.

    # For this function to be useful *during* the loop, it implies we can get immediate retrieval results.
    # The `retrieve_documents` node's output `context` contains List[Document].
    # Let's assume `final_state["context"]` contains the retrieved docs (without scores directly here).
    # Their sources are in `doc.metadata["source"]`.
    
    # For now, this function is a bit of a placeholder for how we get them.
    # The actual retrieval data will be parsed from the log file later.
    # However, for the sake of structure, let's say it could return doc sources for now.
    # This part needs refinement based on how `rag_chain.py` works with logging.
    # The `retrieve_documents` node in `rag_chain.py` *does* return `{"context": retrieved_docs}`.
    # So, `final_state["context"]` should indeed have the retrieved docs.
    
    retrieved_doc_sources = []
    if "context" in final_state and final_state["context"]:
        for doc in final_state["context"]:
            if hasattr(doc, 'metadata') and 'source' in doc.metadata:
                retrieved_doc_sources.append(doc.metadata['source'])
            else:
                # Handle cases where source might be missing, though unlikely for well-formed docs
                retrieved_doc_sources.append("unknown_source_in_get_baseline")
    
    return retrieved_doc_sources[:k_retrieval] # Return top K sources


def calculate_recall_at_k(retrieved_sources: list, golden_sources: list, k: int) -> float:
    """Calculates Recall@K."""
    if not golden_sources: # Avoid division by zero if no golden docs for a question
        return 1.0 if not retrieved_sources else 0.0 # Or handle as appropriate (e.g. 0.0 or skip)
    
    # Take top K retrieved items
    top_k_retrieved = retrieved_sources[:k]
    
    # Count how many golden sources are in the top K retrieved
    # Ensure comparison is robust (e.g., normalize paths if necessary)
    # For now, assuming exact string match from metadata["source"]
    hits = 0
    for golden_source in golden_sources:
        if golden_source in top_k_retrieved:
            hits += 1
            
    recall = hits / len(golden_sources)
    return recall


# --- Run the evaluation loop ---
K_FOR_RECALL = 10 # Recall@10 as per prod.md
baseline_results = []

# Ensure the retrieval log specific to this eval run is empty if it exists
if eval_retrieval_log_file.exists():
    eval_retrieval_log_file.unlink()

# Modify rag_chain.DEFAULT_RETRIEVAL_LOG_PATH for this run
# This is a hacky way to point the RAG chain's logging to our eval log.
# A cleaner solution would be to pass the log path to the RAG chain initialization.
import backend.rag_chain as rag_chain_module
original_rag_log_path = rag_chain_module.DEFAULT_RETRIEVAL_LOG_PATH
rag_chain_module.DEFAULT_RETRIEVAL_LOG_PATH = eval_retrieval_log_file
print(f"Temporarily changed RAG chain retrieval log to: {eval_retrieval_log_file}")

if rag_app and qa_dataset:
    print(f"\nRunning baseline evaluation for {len(qa_dataset)} questions...")
    for i, qa_item in enumerate(qa_dataset):
        question = qa_item["question"]
        query_id = qa_item.get("id", f"eval_q_{uuid.uuid4()}") # Use ID from YAML or generate
        golden_sources = qa_item.get("golden_doc_sources", [])
        
        print(f"  {i+1}/{len(qa_dataset)}: QID {query_id} - {question[:50]}...", end=" ")
        
        # Invoking the RAG graph. This will populate `eval_retrieval_log_file` via the `retrieve_documents` node.
        # And it will also trigger the aep_eval_callback_handler for LLM AEP events.
        invocation_config = {
            "callbacks": [aep_eval_callback_handler],
            "metadata": {"query_id": query_id} 
        }
        initial_state = {"question": question, "query_id": query_id, "context": [], "answer": ""}
        try:
            final_state = rag_app.invoke(initial_state, config=invocation_config)
            # We don't directly use final_state["context"] for recall calculation here,
            # as scores are not in that structure. We'll parse the log file.
        except Exception as e:
            print(f"ERROR invoking RAG for QID {query_id}: {e}")
            # Log error or append a failure marker to results
            continue # Skip to next question on error
        
        print(f"Done.")
        # Small delay between queries if needed
        # time.sleep(0.1)

    print("\nBaseline RAG invocations complete.")
    print(f"Retrieval data logged to: {eval_retrieval_log_file}")

    # --- Now parse the retrieval log to calculate recall ---
    # This log was generated by the `retrieve_documents` node in the RAG chain.
    all_retrieval_log_entries = []
    if eval_retrieval_log_file.exists():
        with open(eval_retrieval_log_file, 'r') as f_log:
            for line in f_log:
                try:
                    all_retrieval_log_entries.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"Warning: Could not parse line in retrieval log: {line.strip()}")
    else:
        print(f"Error: Evaluation retrieval log file not found: {eval_retrieval_log_file}")

    # Create a DataFrame from the retrieval log for easier processing
    df_retrieval_log = pd.DataFrame(all_retrieval_log_entries)
    
    # Join with qa_dataset to get golden_sources for each query_id
    df_qa = pd.DataFrame(qa_dataset)
    # Use the 'id' from qa.yaml as the query_id for joining
    df_eval_data = pd.merge(df_qa, df_retrieval_log, left_on="id", right_on="query_id", how="left")

    recalls_at_k = []
    for index, row in df_eval_data.iterrows():
        retrieved_items = row.get("retrieved_items", []) # This is a list of dicts with {"doc_source": ..., "score": ...}
        if pd.isna(retrieved_items): # Handle cases where a query might not have retrieval results (e.g., error during RAG run)
            retrieved_doc_sources = []
        else:
            # Sort by score (descending, assuming higher is better) before taking top K
            # The RAG chain's similarity_search_with_score already returns sorted items.
            # We just need the sources.
            retrieved_doc_sources = [item["doc_source"] for item in retrieved_items]
            
        golden = row.get("golden_doc_sources", [])
        if not isinstance(golden, list): golden = [] # Ensure it's a list
            
        recall = calculate_recall_at_k(retrieved_doc_sources, golden, K_FOR_RECALL)
        recalls_at_k.append(recall)
        baseline_results.append({
            "query_id": row["id"],
            "question": row["question_x"], # question_x from df_qa after merge
            "retrieved_sources_top_k": retrieved_doc_sources[:K_FOR_RECALL],
            "golden_sources": golden,
            f"recall_@{K_FOR_RECALL}": recall
        })

    df_baseline_results = pd.DataFrame(baseline_results)
    mean_recall_at_k = df_baseline_results[f"recall_@{K_FOR_RECALL}"].mean() if not df_baseline_results.empty else 0

    print(f"\n--- Baseline Recall@{K_FOR_RECALL} --- ")
    print(df_baseline_results[[f"recall_@{K_FOR_RECALL}"]].describe())
    print(f"\nMean Baseline Recall@{K_FOR_RECALL}: {mean_recall_at_k:.4f}")
    
    # Expected baseline from prod.md: ~0.68
    # Target for AEP-weighted: >= 0.77 (+9pp)

else:
    print("Skipping baseline evaluation as RAG app or QA dataset is not available.")

# Restore original rag_chain log path if modified
rag_chain_module.DEFAULT_RETRIEVAL_LOG_PATH = original_rag_log_path
print(f"Restored RAG chain retrieval log to: {original_rag_log_path}")
```

## 5. AEP Data Collection & Processing (Placeholder)

This section will involve:
1.  Running the UI, interacting with documents to generate `human_dwell` AEP events via the `/collect` endpoint. These get logged to `human_dwell_events` ledger by the backend.
2.  Pulling these `human_dwell` AEP events.
3.  Aggregating `focus_ms` per `doc_source` (and `session_id`).

```{code-cell} ipython3
# Placeholder for AEP data loading and processing logic
# human_dwell_ledger = AEPLedger(ledger_name="human_dwell_events")
# all_human_dwell_files = human_dwell_ledger.get_all_ledger_files()
# human_dwell_events = []
# for f_path in all_human_dwell_files:
#     human_dwell_events.extend(human_dwell_ledger.read_events(f_path))
# df_human_dwell = pd.DataFrame(human_dwell_events)

# if not df_human_dwell.empty:
#     # Extract doc_source from payload
#     df_human_dwell["doc_source"] = df_human_dwell["payload"].apply(lambda p: p.get("doc_source") if isinstance(p, dict) else None)
#     # Aggregate focus_ms per doc_source (sum over all sessions for simplicity now)
#     df_doc_focus = df_human_dwell.groupby("doc_source")["focus_ms"].sum().reset_index()
#     df_doc_focus.rename(columns={"focus_ms": "total_doc_focus_ms"}, inplace=True)
#     print("\nAggregated Document Focus Time (Sample):")
#     print(df_doc_focus.head())
# else:
#     print("\nNo human dwell events found to process.")
#     df_doc_focus = pd.DataFrame(columns=["doc_source", "total_doc_focus_ms"]) # Empty for join
```

## 6. AEP-Weighted Re-ranking and Evaluation (Placeholder)

1.  Join the baseline retrieval results with aggregated `doc_focus_ms`.
2.  Apply the AEP weighting formula: `score' = score * (1 + log(1 + doc_focus_ms))`.
3.  Re-calculate Recall@K with the new scores.

```{code-cell} ipython3
# Placeholder for AEP-weighted re-ranking
# df_eval_with_retrieval_scores = ... # This would need baseline scores, not just sources
# For now, let's assume we can join df_baseline_results with df_doc_focus
# and apply weighting. This section requires more detailed dataflow for scores.

# The `df_retrieval_log` contains scores. We need to use that as the base.

# if not df_retrieval_log.empty and not df_doc_focus.empty:
#     # We need to process each query's retrieved_items from df_retrieval_log
#     aep_weighted_results = []
#     for index, eval_row in df_eval_data.iterrows(): # df_eval_data has qa + retrieval log joined
#         query_id = eval_row["id"]
#         question_text = eval_row["question_x"]
#         golden_sources = eval_row.get("golden_doc_sources", [])
#         if not isinstance(golden_sources, list): golden_sources = []
            
#         retrieved_items_with_scores = eval_row.get("retrieved_items", [])
#         if pd.isna(retrieved_items_with_scores) or not isinstance(retrieved_items_with_scores, list):
#             retrieved_items_with_scores = []

#         re_ranked_items = []
#         for item in retrieved_items_with_scores:
#             doc_source = item["doc_source"]
#             baseline_score = item["score"]
            
#             # Get total_doc_focus_ms for this doc_source
#             doc_focus_series = df_doc_focus[df_doc_focus["doc_source"] == doc_source]["total_doc_focus_ms"]
#             doc_focus_ms = doc_focus_series.iloc[0] if not doc_focus_series.empty else 0
            
#             # Apply AEP weighting formula (from prod.md)
#             # score_prime = baseline_score * (1 + np.log1p(doc_focus_ms)) # log1p(x) = log(1+x)
#             # The formula from prod.md: score' = score * (1 + log(1 + doc_focus_ms))
#             # Using np.log for natural log. If base 10, use np.log10.
#             # Assuming natural log as common in such formulas.
#             weight = 1 + np.log(1 + doc_focus_ms) # Ensure doc_focus_ms is not negative; it shouldn't be.
#             aep_score = baseline_score * weight
            
#             re_ranked_items.append({"doc_source": doc_source, "baseline_score": baseline_score, "aep_score": aep_score, "doc_focus_ms": doc_focus_ms})
        
#         # Sort by new aep_score (descending)
#         re_ranked_items_sorted = sorted(re_ranked_items, key=lambda x: x["aep_score"], reverse=True)
#         aep_retrieved_sources_top_k = [item["doc_source"] for item in re_ranked_items_sorted[:K_FOR_RECALL]]
        
#         aep_recall = calculate_recall_at_k(aep_retrieved_sources_top_k, golden_sources, K_FOR_RECALL)
#         aep_weighted_results.append({
#             "query_id": query_id,
#             "question": question_text,
#             "aep_retrieved_sources_top_k": aep_retrieved_sources_top_k,
#             "golden_sources": golden_sources,
#             f"aep_recall_@{K_FOR_RECALL}": aep_recall,
#             "details": re_ranked_items_sorted # For inspection
#         })

#     df_aep_results = pd.DataFrame(aep_weighted_results)
#     if not df_aep_results.empty:
#         mean_aep_recall_at_k = df_aep_results[f"aep_recall_@{K_FOR_RECALL}"].mean()
#         print(f"\n--- AEP-Weighted Recall@{K_FOR_RECALL} --- ")
#         print(df_aep_results[[f"aep_recall_@{K_FOR_RECALL}"]].describe())
#         print(f"\nMean AEP-Weighted Recall@{K_FOR_RECALL}: {mean_aep_recall_at_k:.4f}")
        
#         lift = mean_aep_recall_at_k - mean_recall_at_k
#         print(f"Recall Lift (AEP - Baseline): {lift:.4f} ({lift*100:.2f} pp)")
#         # Target: +9pp (0.09)
#     else:
#         print("Could not compute AEP-weighted results. Check data.")

# else:
#     print("Skipping AEP-weighted evaluation due to missing retrieval log or doc focus data.")
```

## 7. Sanity Plots (Placeholders)

Visualize distributions and comparisons.

```{code-cell} ipython3
# # Plot 1: Histogram of human_dwell_ms (if available)
# if not df_doc_focus.empty and "total_doc_focus_ms" in df_doc_focus.columns:
#     plt.figure(figsize=(10, 6))
#     sns.histplot(df_doc_focus["total_doc_focus_ms"], bins=30, kde=True)
#     plt.title('Distribution of Aggregated Human Dwell Time per Document')
#     plt.xlabel('Total Focus ms (Human Dwell)')
#     plt.ylabel('Frequency')
#     plt.show()
# else:
#     print("No human dwell data to plot histogram.")

# # Plot 2: Scatter baseline vs. weighted scores (if AEP re-ranking is done)
# # This requires scores for individual items from re_ranked_items_sorted within df_aep_results
# if 'df_aep_results' in locals() and not df_aep_results.empty:
#     all_ranked_details = []
#     for detail_list in df_aep_results["details"]:
#         all_ranked_details.extend(detail_list)
#     df_plot_scores = pd.DataFrame(all_ranked_details)
    
#     if not df_plot_scores.empty:
#         # Add ground truth info if possible (complex join)
#         plt.figure(figsize=(10, 8))
#         sns.scatterplot(data=df_plot_scores, x="baseline_score", y="aep_score", hue="doc_focus_ms", size="doc_focus_ms", sizes=(20,200), alpha=0.7)
#         plt.title('Baseline Score vs. AEP-Weighted Score')
#         plt.xlabel('Baseline Retrieval Score')
#         plt.ylabel('AEP-Weighted Score')
#         # Add a y=x line for reference
#         max_val = max(df_plot_scores["baseline_score"].max(), df_plot_scores["aep_score"].max())
#         min_val = min(df_plot_scores["baseline_score"].min(), df_plot_scores["aep_score"].min())
#         plt.plot([min_val, max_val], [min_val, max_val], 'k--', lw=1)
#         plt.grid(True, linestyle='--', alpha=0.7)
#         plt.legend(title='Doc Focus MS')
#         plt.show()
#     else:
#         print("No score data for scatter plot.")
# else:
#     print("No AEP results to plot scores.")
```

## 8. Conclusion & Next Steps

Summarize findings. The target is Recall@10 (AEP-weighted) >= 0.77 (+9pp lift over baseline ~0.68).
