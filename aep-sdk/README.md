# AEP SDK (Attention Event Protocol)

This SDK provides tools for logging user and system attention (focus time) and utilizing these signals, for example, to improve RAG system relevance.

## Overview

Key components:
- **`aep.AEPLedger`**: Manages writing AEP events (MsgPack format) to rotating, gzipped ledger files.
- **`aep.AEPCallbackHandler`**: A LangChain callback to automatically log LLM execution latency as AEP events.
- **`aep.cli`**: Command-line tools to inspect and merge AEP ledgers.
- **Backend Example**: A FastAPI server demonstrating collection of human dwell time AEPs and a RAG query endpoint instrumented with AEP logging.
- **UI Example (Conceptual)**: Code for a React component to track human dwell time on document sections.
- **Evaluation Framework**: Tools and scripts to evaluate the impact of AEPs on RAG retrieval (Recall@K).

## Getting Started in 60 Seconds (Local Development)

1.  **Clone the Repository:**
    ```bash
    git clone <repository_url> # Replace with your repo URL
    cd aep-sdk
    ```

2.  **Set up Python Environment (using Python 3.11):**
    ```bash
    python3.11 -m venv .venv
    source .venv/bin/activate 
    ```
    *(On Windows: `.venv\Scripts\activate`)*

3.  **Install Dependencies with Poetry:**
    ```bash
    # Install poetry if you haven't: https://python-poetry.org/docs/#installation
    poetry install --all-extras # Install main, dev, and other dependencies
    ```

4.  **Set OpenAI API Key:**
    Ensure the `OPENAI_API_KEY` environment variable is set.
    ```bash
    export OPENAI_API_KEY="sk-..."
    ```
    *(Or set it in your shell's profile, or use a .env file if the app supports it - current backend checks env var)*

5.  **Copy Document Corpus for RAG:**
    The RAG system needs documents to operate on. If you have the `aep-demo` PoC project, copy its docs:
    ```bash
    # Assuming aep-demo is a sibling directory to aep-sdk
    cp -r ../aep-demo/docs ./docs 
    ```
    If not, create a `docs/` directory in `aep-sdk/` and add some `.md` or `.mdx` files.

6.  **Run the Backend API Server:**
    ```bash
    poetry run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
    ```
    You should see logs indicating the FastAPI server is running and the RAG graph is being initialized.

7.  **Next Steps (Manual for UI and Full Test):**
    *   **UI Setup**: Navigate to `ui/`, scaffold a Vite+React+TS app, replace `App.tsx` etc., install npm deps (`npm ci`), configure `vite.config.ts` proxy, and run (`npm run dev`). Access at `http://localhost:5173` (or Vite's port).
    *   **Populate QA Set**: Edit `qa/qa.yaml` to have ~100 high-quality questions based on your `docs/` content.
    *   **Run Evaluation Notebook/Script**: Convert `analysis/eval_notebook_content.md` to `analysis/eval.ipynb` and run it, or run `python analysis/run_eval.py`.
    *   **Full Smoke Test with Docker Compose**: (Requires Docker Desktop)
        ```bash
        # Ensure OPENAI_API_KEY is available in your environment for docker compose
        docker compose up --build
        ```
        Access UI at `http://localhost:3000`, API at `http://localhost:8000`, Jupyter at `http://localhost:8888`.

## Key Features

*   **AEP Event Logging**: Capture LLM latency and human dwell time.
*   **RAG Integration**: Example backend demonstrating AEPs in a RAG pipeline.
*   **CLI Tools**: Utilities for managing AEP ledger files.
*   **Evaluation**: Framework for measuring retrieval performance.

## Project Structure

```
aep-sdk/
├── aep/            # Core SDK (Python package)
│   ├── __init__.py
│   ├── callback.py   # LangChain AEP callback handler
│   ├── cli.py        # Command-line interface
│   ├── ledger.py     # AEP event ledger management
│   └── tests/        # Unit tests for the SDK
├── analysis/       # Evaluation scripts and notebooks
│   ├── eval_notebook_content.md
│   └── run_eval.py
├── backend/        # FastAPI backend application
│   ├── __init__.py
│   ├── main.py       # FastAPI app, /collect and /rag/query endpoints
│   └── rag_chain.py  # RAG logic
├── docs/           # Document corpus for RAG (to be populated)
├── qa/             # Question-Answering evaluation sets
│   └── qa.yaml
├── scripts/        # Utility scripts (e.g., build_qa.py)
│   └── build_qa.py
├── ui/             # React front-end application (conceptual code provided)
│   ├── Dockerfile
│   ├── src/
│   │   ├── App.css
│   │   ├── App.tsx
│   │   ├── index.tsx
│   │   └── vite-env.d.ts
│   └── ... (vite config, package.json etc. to be created by user)
├── .github/        # GitHub Actions workflows
│   └── workflows/
│       └── ci.yml
├── .dockerignore
├── Dockerfile.api  # Dockerfile for the backend API
├── docker-compose.yml
├── poetry.lock
├── pyproject.toml
└── README.md
```

(More details on configuration, advanced usage, and contribution to follow.)

## Troubleshooting

*   **`faiss.swig` or FAISS build error during `poetry install` or `pip install faiss-cpu`:**
    *   Ensure you are using **Python 3.11**. FAISS wheels are not always available for other versions (like 3.12) on all platforms, leading to build failures.
    *   Make sure SWIG is installed on your system (`brew install swig` on macOS, `sudo apt-get install swig` on Debian/Ubuntu).
    *   For Linux, ensure C++ build tools and potentially OpenMP libraries (`libomp-dev`) are installed.

(More troubleshooting tips to be added as needed.) 