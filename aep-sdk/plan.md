# AEP-SDK v0.1 Readiness Test Plan (derived from user's 5-layer plan)

This plan outlines the steps to verify the AEP-SDK v0.1 release readiness.

– TASK: Prerequisite User Tasks (Manual)
– ETA: User-dependent (estimate 2-4 hrs)
– DEPENDENCIES: Node.js/npm/yarn, Docker Desktop, OpenAI API Key.
– DETAILS:
    1. UI: Scaffold Vite project in `aep-sdk/ui/`, install npm deps, integrate provided React code, verify Vite dev proxy (`vite.config.ts`).
    2. QA Set: Manually curate `aep-sdk/qa/qa.yaml` to ~100 high-quality questions (after running `scripts/build_qa.py`).
    3. Notebook: Convert `aep-sdk/analysis/eval_notebook_content.md` to `eval.ipynb`.
    4. Commit `poetry.lock` to repository.
    5. Copy `aep-demo/docs` to `aep-sdk/docs` if not already done.
– OPEN QUESTIONS: None for agent; user to confirm completion.

– TASK: Layer 1 · Python unit tests
– ETA: < 15 min
– DEPENDENCIES: Prerequisite User Tasks completed, Poetry environment set up.
– COMMAND: `poetry run pytest -q` (also consider `poetry run ruff check aep backend` if linters are set up).
– PASS CRITERIA: All tests green.
– OPEN QUESTIONS: None.

– TASK: Layer 2 · Headless eval
– ETA: < 15 min
– DEPENDENCIES: Layer 1 passed, OpenAI API Key available, `docs/` populated, `qa/qa.yaml` curated.
– COMMAND: `OPENAI_API_KEY=sk-... poetry run python analysis/run_eval.py`
– PASS CRITERIA: Script exits 0, prints Recall@10 >= 0.68.
– OPEN QUESTIONS: None.

– TASK: Layer 3 · Local dev stack interactive test
– ETA: 30 min
– DEPENDENCIES: Layer 2 passed, UI scaffolded and runnable (`npm run dev`).
– COMMAND: 
    ```bash
    # Terminal 1
    OPENAI_API_KEY=sk-... poetry run uvicorn backend.main:app --reload
    # Terminal 2
    cd ui && npm ci && npm run dev
    ```
    Then, interact in browser: ask questions, check UI response, check ledger growth (`aep inspect data/.aep/*_llm_events.aep` and `human_dwell_events.aep`).
– PASS CRITERIA: Answers in UI, both LLM and human dwell ledgers grow.
– OPEN QUESTIONS: None.

– TASK: Layer 4 · Docker compose smoke test
– ETA: 30 min (includes build time)
– DEPENDENCIES: Layer 3 passed, Docker Desktop running, `.env` file with `OPENAI_API_KEY` (or key passed directly).
– COMMAND: 
    ```bash
    docker compose build --parallel
    docker compose up -d
    ```
    Then check API health (e.g., `curl http://localhost:8000/` or a dedicated `/health` if added), UI loads at `http://localhost:3000` and queries succeed.
– PASS CRITERIA: `api` healthy, UI loads and queries function.
– OPEN QUESTIONS: Need for a dedicated `/health` endpoint in FastAPI app.

– TASK: Layer 5 · CI dry-run simulation
– ETA: 15 min (plus CI run time)
– DEPENDENCIES: Layer 4 passed, code committed to a branch.
– COMMAND: `git checkout -b smoke && git commit --allow-empty -m "test: CI smoke test trigger" && git push origin smoke`
– PASS CRITERIA: GitHub Action completes successfully (green), `aep-ledger` artifact uploaded and inspectable.
– OPEN QUESTIONS: None.

– TASK: Final Release Steps (v0.1.0)
– ETA: < 1 hr
– DEPENDENCIES: All 5 layers passed.
– DETAILS: Tag `v0.1.0`, push tag, prepare release notes (if any), invite first beta users.
– OPEN QUESTIONS: None. 

- TASK: integrate a re-ranking / filtering stage between retrieval and answer generation that reduces context length while preserving recall
  ETA: 2-3 hrs
  DEPENDENCIES: backend/rag_chain.py, additional similarity or LLM scoring module
  OPEN QUESTIONS: use simple cosine-sim threshold vs. LLM cross-encoder?

- TASK: update RAG graph unit tests to verify re-ranking behaviour (precision ↑, context length ↓)
  ETA: 1 hr
  DEPENDENCIES: pytest, small synthetic corpus
  OPEN QUESTIONS: test K values?

- TASK: run `analysis/compare_retrieval_quality.py` before & after re-ranking and capture metrics table
  ETA: <15 min
  DEPENDENCIES: OPENAI_API_KEY, FAISS index rebuilt
  OPEN QUESTIONS: acceptable precision improvement threshold?

- TASK: convert compare script into a lightweight Jupyter Notebook for publication (includes cell to pretty-print ledger events)
  ETA: 45 min
  DEPENDENCIES: jupyter, ipywidgets (optional)
  OPEN QUESTIONS: add bar-chart visual?

- TASK: add `aep cli verify` sub-command that prints summary stats from the latest ledger (mean context length, unique docs, etc.)
  ETA: 1.5 hrs
  DEPENDENCIES: aep/cli.py
  OPEN QUESTIONS: which stats are most compelling for users?

- TASK: write README section / blog snippet explaining Nixon 1971 attention-economy link and how AEP operationalises it for end-users
  ETA: 1 hr
  DEPENDENCIES: none
  OPEN QUESTIONS: historical references to cite? 