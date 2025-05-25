“AEP-SDK v0.1” Build Sprint — Next-Step Master Doc

Audience: a fresh coding agent with zero context.
Goal: turn last week’s PoC into a pip-installable SDK + multi-framework demo that real users can try in <10 min and submit real-world attention traces.

⸻

0 · TL;DR (what we will ship this time)
	•	SDK: pip install aep → gives AEPCallback, AEPBrowserTap, CLI tools.
	•	Full-stack demo: RAG chat + tiny React front-end that logs true dwell-time per retrieved doc.
	•	Eval notebook: proves per-document focus re-ranking lifts Recall@10 on a 100-question LangChain QA set (+9 pp target).
	•	Telemetry flow: user runs aep pull ~/.aep/*.aep → uploads anonymised bundle to DuckDB / Grafana dashboard.

Deliverables live in aep-sdk/ branch; Docker Compose one-liner still works.

⸻

1 · What this build is

Section	Short description	Delta vs PoC
Docs corpus	Same LangChain dump but include page-level URL in metadata	needed for browser tap
Front-end	/ui/ React app with markdown viewer; attaches IntersectionObserver + pagehide to emit {doc_source, dwell_ms} via /collect endpoint	real human focus
Back-end	FastAPI server: routes → RAG chain (unchanged) plus /collect POST that writes AEP lines with focus_kind="human_dwell"	joins UX & LLM traces
SDK core	/aep/ package:  • AEPCallback (LLM)• AEPLedger (append/gzip/rotate)• aep cli (inspect, merge, upload)	production-ready
Per-doc weighting	new formula: score' = score * (1 + log1p(doc_focus_ms)) where doc_focus_ms = Σ human dwell for that doc within session window	actually re-orders top-k
Evaluation harness	100 canonical Q/A pairs (ported from LangChain docs qa.yaml) + script to auto-run queries and write a retrieval.tsv for baseline vs weighted	automated metric
CI·CD	GitHub Actions: lint, pytest, run harness, fail if Recall@10 < baseline	keeps bar green
Docs site	Docusaurus under /website, auto-deploy on gh-pages	user-facing


⸻

2 · Why this step matters
	1.	Real attention, not a proxy – we prove the signal survives noisy human scroll time.
	2.	Per-document granularity – weighting finally changes ranking inside a single query.
	3.	Install friction ≈ zero – devs can drop one callback + one JS snippet; no cloud needed.
	4.	Data pipeline future-proof – .aep lines are mergeable; SDK CLI merges mobile, Discord, whatever.

⸻

3 · Tech spec (pin versions)

python==3.11
fastapi==0.111.*
uvicorn[standard]==0.29.*
langchain==0.1.*
openai==1.23.*
faiss-cpu==1.7.*
msgpack==1.0.*
duckdb==1.*
numpy, pandas, matplotlib
react==18 (frontend)

File tree

aep-sdk/
├─ aep/                       # pip package
│   ├─ __init__.py
│   ├─ callback.py            # AEPCallback (LLM)
│   ├─ ledger.py              # AEPLedger class
│   └─ cli.py                 # inspect/merge/upload
├─ backend/
│   ├─ main.py                # FastAPI app
│   └─ rag_chain.py           # imports callback
├─ ui/                        # React SPA
│   ├─ src/App.tsx            # markdown viewer + dwell hook
│   └─ public/index.html
├─ docs/                      # markdown corpus
├─ qa/qa.yaml                 # 100 Q/A pairs
├─ analysis/
│   └─ eval.ipynb
├─ docker-compose.yml         # api + front + jupyter
└─ .github/workflows/ci.yml

AEP line formats

LLM event (unchanged)

{
  "id": "<sha256(payload)>",
  "ts": 1716401200.123,
  "focus_ms": 512,               // exec latency
  "payload": {"role":"assistant","content":"..."},
  "focus_kind": "exec_latency",
  "query_id": "query_<uuid4>"
}

Human dwell event (new)

{
  "id": "<sha256(doc_source + session_id)>",
  "ts": 1716401202.456,
  "focus_ms": 2400,              // intersection observer
  "payload": {"doc_source":"docs/concepts/agents.mdx"},
  "focus_kind": "human_dwell",
  "session_id": "<uuid4>"
}


⸻

4 · Two-day sprint schedule (EDT)

Time	Task	Owner/notes
Day 1 19:00–20:00	Repo restructure, poetry init, copy PoC code	
20:00–21:30	Implement AEPLedger w/ gzip rotation & CLI	
21:30–22:30	Port AEPCallback to package; write unit tests	
22:30–23:30	FastAPI skeleton + /collect route, mount ledger	
Day 2 09:00–10:30	React viewer: markdown render, scroll tracker → Beacon	
10:30–11:30	Per-doc focus aggregation util	
11:30–13:00	Eval script: run 100 QA; dump retrieval.tsv	
13:00–14:00	Notebook: baseline vs weighted Recall@10 plot	target +9 pp
14:00–15:00	GitHub Actions CI (black + pytest + eval)	
15:00–16:00	Write docs/Quickstart.md & website deploy	
16:00–17:00	Final polish, push, tag v0.1.0	


⸻

5 · Measurement cheat-sheet v2
	•	Per-doc weighting

score’ = score \times \bigl(1 + \log\bigl(1 + \mathrm{doc\_focus\_ms} \bigr)\bigr)
	•	Metric

Recall@10 on 100-item QA set.
Baseline expected ≈ 0.68 → goal ≥ 0.77.
	•	Sanity plots

	1.	Histogram of human_dwell → should follow a long-tail (>5 s med on top docs).
	2.	Scatter baseline vs weighted with colour = ground-truth.

⸻

6 · Context blurb for brand-new teammates

“AEP logs” are append-only MsgPack lines that say how long either the model (exec latency) or the human (scroll dwell) paid attention to something.  We proved last week that any attention signal can re-rank RAG results.  This sprint we’re adding real browser dwell, packaging it as an SDK, and shipping an end-to-end demo so outside devs can try the loop and send us their traces.

⸻

7 · Kick-off commands

git clone https://github.com/YOURORG/aep-sdk && cd aep-sdk
docker compose up             # api at :8000, UI at :3000, Jupyter at :8888
# In another shell
poetry install && poetry run pytest

Open analysis/eval.ipynb, run all cells → expect:

Recall@10 (baseline): 0.68
Recall@10 (AEP-weighted): 0.77  (+9 pp)

Screenshot that graph, tweet it, and we’re ready for alpha testers.