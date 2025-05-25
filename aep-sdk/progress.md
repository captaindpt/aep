– TIMESTAMP: 2024-07-29 10:00
– WHAT: Initialized AEP-SDK project structure and core components.
– DETAILS: Created `aep-sdk` directory with subdirs for `aep` (SDK), `backend`, `ui`, `qa`, `analysis`. Implemented `AEPLedger` with rotation/gzipping, `AEPCallbackHandler` using the ledger, and basic CLI (`inspect`, `list`). Added unit tests for ledger and callback. Set up Poetry with Python 3.11.
– RESOURCES: `aep-sdk/`, `aep-sdk/aep/`, `aep-sdk/pyproject.toml`

– TIMESTAMP: 2024-07-29 10:15
– WHAT: Developed FastAPI backend skeleton with RAG integration.
– DETAILS: Created `backend/main.py` with `/collect` endpoint for human dwell events and `/rag/query` endpoint. Ported RAG logic from PoC to `backend/rag_chain.py` using FAISS. RAG graph and AEP callback are initialized on FastAPI startup. Added relevant dependencies (FastAPI, Uvicorn, LangChain, FAISS, etc.) to `pyproject.toml`.
– RESOURCES: `aep-sdk/backend/main.py`, `aep-sdk/backend/rag_chain.py`, `aep-sdk/pyproject.toml`

– TIMESTAMP: 2024-07-29 10:30
– WHAT: Drafted React front-end components and evaluation notebook structure.
– DETAILS: Provided code for `ui/src/App.tsx` (dwell tracking & beacon), `ui/src/index.tsx`, and `ui/src/App.css`. Created `qa/qa.yaml` structure with examples. Drafted `analysis/eval_notebook_content.md` for baseline Recall@K evaluation and AEP re-ranking placeholders. Added notebook dependencies to `pyproject.toml`.
– RESOURCES: `aep-sdk/ui/src/`, `aep-sdk/qa/qa.yaml`, `aep-sdk/analysis/eval_notebook_content.md`

– TIMESTAMP: 2024-07-29 11:00
– WHAT: Applied run-book v2 updates for AEP-SDK v0.1.
– DETAILS: Pinned Python to 3.11.*, updated CI for libomp-dev, hardened build_qa.py (dedupe, filter, paths), added portalocker to AEPLedger, added merge CLI unit test, updated Dockerfile.api, created .dockerignore, created analysis/run_eval.py script, updated README.md with Getting Started.
– RESOURCES: `aep-sdk/pyproject.toml`, `aep-sdk/.github/workflows/ci.yml`, `aep-sdk/scripts/build_qa.py`, `aep-sdk/aep/ledger.py`, `aep-sdk/aep/tests/test_cli.py`, `aep-sdk/Dockerfile.api`, `aep-sdk/.dockerignore`, `aep-sdk/analysis/run_eval.py`, `aep-sdk/README.md`

– TIMESTAMP: 2024-07-29 11:30
– WHAT: Applied run-book v3 (Quick-scan verdict) updates.
– DETAILS: Updated CI (apt-get update -y, artifact upload), added TODO for AEPLedger batching, improved build_qa.py pathing, added CLI merge test for timestamp sort, updated .dockerignore for notebooks, updated Dockerfile.api for pip cache clear, updated run_eval.py for CI API key skip & logging, updated README with FAISS troubleshooting.
– RESOURCES: `aep-sdk/.github/workflows/ci.yml`, `aep-sdk/aep/ledger.py`, `aep-sdk/scripts/build_qa.py`, `aep-sdk/aep/tests/test_cli.py`, `aep-sdk/.dockerignore`, `aep-sdk/Dockerfile.api`, `aep-sdk/analysis/run_eval.py`, `aep-sdk/README.md`

– TIMESTAMP: 2024-07-29 12:00
– WHAT: Expanded curated QA benchmark to 110 questions.
– DETAILS: Added 85 new high-quality question-answer entries (Q025-Q109) covering toolkits, rate-limits, Runnables, LangGraph, streaming, caching, integrations, etc. Updated current.md to reflect in-progress status.
– RESOURCES: `aep-sdk/qa/qa_curated.yaml`, `aep-sdk/current.md` 

QA Set: ✅ Completed – curated to 110 questions, renamed to `qa/qa.yaml`, evaluation recall 0.7591 (pass).

Evaluation RAG invocations complete. Retrieval data logged to: /Users/manirashahmadi/ccode/aep/aep-sdk/data/evaluation_run/ci_retrieval_log_20250521-203115.jsonl
Restored RAG chain retrieval log to: /Users/manirashahmadi/ccode/aep/aep-sdk/data/retrieval_log.jsonl

Mean Baseline Recall@10: 0.7591
Final Mean Recall@10: 0.7591
Recall@10 (0.7591) meets or exceeds threshold (0.6800). Evaluation PASSED.

– TIMESTAMP: 2023-10-27 10:00
– WHAT: Created `convert_notebook.py` script for two-way conversion between Markdown and Jupyter Notebook formats.
– DETAILS: The script uses the `jupytext` library and supports command-line arguments for input and output files. It can convert `.md` to `.ipynb` and vice-versa, inferring output filenames if not provided.
– RESOURCES: `convert_notebook.py`

– TIMESTAMP: 2023-10-27 10:30
– WHAT: Modified `analysis/convert_notebook.py` to handle cell outputs correctly.
– DETAILS: When converting IPYNB to MD, the script now uses `md:myst` format to ensure outputs are included in the Markdown file. Conversion from plain MD to IPYNB correctly continues to generate notebooks without pre-existing outputs.
– RESOURCES: `analysis/convert_notebook.py`

– TIMESTAMP: 2023-10-27 10:45
– WHAT: Further modified `analysis/convert_notebook.py` to explicitly include outputs.
– DETAILS: Added `outputs=True` to `jupytext.write` call when converting from IPYNB to MD (using `md:myst` format). This ensures cell outputs, including tracebacks, are preserved in the text-based Markdown file.
– RESOURCES: `analysis/convert_notebook.py`

– TIMESTAMP: 2023-10-27 11:00
– WHAT: Diagnosed `jupytext.read()` behavior in `analysis/convert_notebook.py`.
– DETAILS: Added in-memory inspection of the notebook object. Confirmed via user-provided debug output that `jupytext.read()` successfully loads cell outputs (including tracebacks) from the `.ipynb` file into memory.
– RESOURCES: `analysis/convert_notebook.py`, User-provided terminal output.

– TIMESTAMP: 2023-10-27 11:30
– WHAT: Investigated `jupytext.write` behavior for output inclusion.
– DETAILS: User provided `jupytext --version` as 1.17.1. Confirmed that with this version, `jupytext.write` does NOT include cell outputs in text-based formats (`md:myst`, `py:percent`) even when `outputs=True` is specified and outputs are confirmed to be read into memory. This suggests a version-specific issue or limitation with `jupytext 1.17.1` for these formats.
– RESOURCES: `analysis/convert_notebook.py`, User-provided `jupytext` version and `eval.py` content.

– TIMESTAMP: 2023-10-27 12:00

– TIMESTAMP: 2025-05-23 00:00
– WHAT: Integrated a filtering stage into the RAG pipeline in `backend/rag_chain.py`.
– DETAILS: Modified `retrieve_documents` to fetch K=15 items. Added a `filter_top_n_documents` node to select the top N=3 documents based on FAISS scores (L2 distance). Updated RAG graph to include this filter between retrieval and generation. `RAGState` was modified to pass `raw_retrieved_docs_with_scores`. Initial call in `if __name__ == '__main__'` was updated.
– RESOURCES: `backend/rag_chain.py`

– TIMESTAMP: 2025-05-23 00:25
– WHAT: Refined `AEPCallbackHandler._process_io_for_logging` to handle `raw_retrieved_docs_with_scores`.
– DETAILS: Added specific logic to `_process_io_for_logging` in `aep/callback.py` to correctly serialize Document objects within the `List[tuple[Document, float]]` structure stored in the `raw_retrieved_docs_with_scores` field of the RAG state. This addresses a `TypeError` during msgpack serialization.
– RESOURCES: `aep/callback.py`

– TIMESTAMP: 2025-05-23 00:30
– WHAT: Further refined `AEPCallbackHandler._process_io_for_logging` to convert numpy.float32 scores.
– DETAILS: Modified the handling of scores within the `raw_retrieved_docs_with_scores` field in `aep/callback.py`. Added logic to check for `.item()` method (for numpy scalars) and then attempt `float()` conversion to ensure scores are standard Python floats before serialization. This addresses a `TypeError` related to `numpy.float32`.
– RESOURCES: `aep/callback.py`