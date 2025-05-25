# AEP (Attention Event Protocol) - Project Archive

> **Archive Notice**: This repository contains development work on the Attention Event Protocol (AEP) system for improving LLM and RAG applications through attention tracking. This is archived research/prototype code, not a production system.

## What is AEP?

The Attention Event Protocol (AEP) is a logging framework that captures how long humans or AI agents actually focus on pieces of data. The core insight is that attention time can be used as a signal to improve AI system performance, particularly in Retrieval Augmented Generation (RAG) applications.

### Core Concept

AEP events are structured as:
```json
{
  "id": "sha256(payload)",        // Content hash for deduplication
  "ts": 1678886400.12345,         // UTC timestamp
  "focus_ms": 1234,               // Attention duration in milliseconds
  "payload": { ... },             // The actual content
  "focus_kind": "exec_latency"    // Type of attention event
}
```

By tracking attention patterns, systems can:
- Re-rank search results based on what users actually engage with
- Improve RAG retrieval relevance using historical attention data
- Provide observability into human-AI interaction patterns

## Repository Structure

This archive contains several components:

### 📦 `aep-sdk/` - Production SDK
The main SDK implementation with:
- **Core SDK** (`aep/`): Python package for AEP event logging and management
- **Backend** (`backend/`): FastAPI server with RAG integration and AEP collection
- **UI** (`ui/`): React components for tracking human dwell time
- **Analysis** (`analysis/`): Evaluation framework for measuring AEP impact
- **QA** (`qa/`): Question-answer datasets for evaluation

Key features:
- `AEPLedger`: Rotating, compressed event storage
- `AEPCallbackHandler`: LangChain integration for automatic LLM latency logging
- CLI tools for ledger inspection and management
- Docker Compose stack for full deployment

### 🧪 `aep-demo/` - Proof of Concept
Initial prototype demonstrating the concept:
- Simple RAG application using LangChain + OpenAI
- AEP callback handler logging LLM execution latency
- Jupyter notebook showing attention-weighted re-ranking
- Grafana dashboard for visualizing attention patterns

### 📊 `llm-records/` - Development Logs
Project planning and progress tracking:
- Original POC specification (`poc.md`)
- Development progress logs
- Planning documents

### 🛠 `scripts/` - Utilities
Helper scripts for data processing and QA generation.

### 📈 `qa/` - Question-Answer Datasets
Evaluation datasets for testing retrieval performance.

## Quick Start (Demo)

To run the proof-of-concept demo:

```bash
cd aep-demo
docker compose up --build
```

This starts:
- JupyterLab at http://localhost:8888
- Grafana at http://localhost:3001

See `aep-demo/README.md` for detailed instructions.

## Development History

This project evolved through several phases:

1. **Initial POC** (aep-demo): Basic proof-of-concept showing attention weighting can improve RAG precision
2. **SDK Development** (aep-sdk): Production-ready SDK with comprehensive tooling
3. **Evaluation Framework**: Tools for measuring AEP impact on retrieval quality

Key achievements:
- Demonstrated attention-weighted re-ranking improving Precision@5 from ~0.75 to ~0.87
- Built production-ready SDK with proper packaging and testing
- Created evaluation framework showing Recall@10 of 0.76+ on curated QA sets
- Implemented filtering/re-ranking pipeline reducing context length while preserving recall

## Technical Stack

- **Python 3.11** (FAISS compatibility requirement)
- **LangChain** for RAG pipeline integration
- **OpenAI API** for embeddings and chat completions
- **FAISS** for vector similarity search
- **MsgPack** for efficient event serialization
- **FastAPI** for backend API
- **React + TypeScript** for frontend
- **Docker Compose** for deployment
- **Poetry** for dependency management

## Key Insights

1. **Attention as Signal**: LLM execution latency and human dwell time provide actionable signals for improving AI systems
2. **Mergeable Events**: Content-addressed event IDs enable collision-free logging from multiple sources
3. **Observability**: Real-time attention tracking provides valuable insights into system performance
4. **Retrieval Enhancement**: Attention-weighted re-ranking can significantly improve retrieval precision

## Archive Status

This code represents research and development work on attention-based AI improvement. The concepts and implementations here informed later production systems but should be treated as experimental/prototype code.

### What Works
- Basic AEP event logging and aggregation
- LangChain integration for automatic LLM latency tracking
- Proof-of-concept attention-weighted re-ranking
- Evaluation framework for measuring impact

### Limitations
- Prototype/research quality code
- Limited production hardening
- Specific to experimental use cases
- Dependencies may be outdated

## License

See individual component directories for specific licensing information.

## References

The project draws inspiration from the economic concept of attention as a scarce resource, applying it to improve AI system performance through empirical attention measurement. 