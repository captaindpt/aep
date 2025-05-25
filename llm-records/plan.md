– TASK: Stage A PoC - "Self-supervised" lift (COMPLETE)
– ETA: <Completed>
– DEPENDENCIES: LangChain RAG, AEP callback, Simulated Dwell, Mini Ground Truth, Jupyter Notebook.
– OPEN QUESTIONS: None for Stage A.

– TASK: Stage B - Ground-truth lift with full QA set (Weekend Sprint)
– ETA: 4-6 hrs (weekend)
– DEPENDENCIES: LangChain docs (for QA set), `retrieval_log.jsonl` from `app.py`, existing analysis notebook.
– OPEN QUESTIONS:
    – Finalize exact 15 FAQ-style Q/A pairs from LangChain docs.
    – Confirm specific page slugs for golden docs for each Q/A.
    – Decide between P@5 and MAP as the primary metric for final reporting (or show both).

– TASK: Notebook Cleanup & Refinement for Stage A Deliverable
– ETA: <1 hr
– DEPENDENCIES: `aep-demo/analysis/focus_weighting.ipynb`
– OPEN QUESTIONS:
    – How to best document the 0 P@5 lift for per-query vs. positive lift for Global Recall@K?
    – Finalize the K value and wording for the "one-liner summary" slide.

– TASK: Grafana Visualization Update (Optional Polish)
– ETA: 1-2 hrs
– DEPENDENCIES: Grafana instance, `dashboard.json`, `demo.aep` (with simulated dwell).
– OPEN QUESTIONS: Does the current dashboard.json effectively visualize the varied `focus_ms` (exec + simulated dwell)?

– TASK: README Update for Stage A
– ETA: 1 hr
– DEPENDENCIES: Completed Stage A, notebook screenshots/results (Global Recall lift).
– OPEN QUESTIONS: How to clearly explain the simulated dwell for PoC purposes?

– TASK: Final Polish & GitHub Push for Stage A Artifact
– ETA: 1 hr
– DEPENDENCIES: All Stage A components, updated README.
– OPEN QUESTIONS: None. 