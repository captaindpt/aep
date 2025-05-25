from fastapi import FastAPI, HTTPException, Body, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
import time
import hashlib
# import msgpack # Not directly used here anymore
from pathlib import Path
import uuid # For generating query_id
import os # For checking OPENAI_API_KEY
from contextlib import asynccontextmanager # Added for lifespan

from langgraph.graph import StateGraph # For type hinting the graph

# Assuming the aep package is installed or in PYTHONPATH
try:
    from aep.ledger import AEPLedger
    from aep.callback import AEPCallbackHandler
    from .rag_chain import get_initialized_rag_graph, RAGState, DEFAULT_DOCS_PATH as RAG_DEFAULT_DOCS_PATH
except ImportError:
    import sys
    # This fallback is for when running main.py directly and backend isn't seen as a package part of aep-sdk
    # This setup assumes that `aep-sdk` is in sys.path or `aep` and `backend` are sibling packages.
    sdk_root = Path(__file__).parent.parent.resolve()
    sys.path.insert(0, str(sdk_root)) 
    from aep.ledger import AEPLedger
    from aep.callback import AEPCallbackHandler
    from backend.rag_chain import get_initialized_rag_graph, RAGState, DEFAULT_DOCS_PATH as RAG_DEFAULT_DOCS_PATH

# --- Environment Check ---
if not os.environ.get("OPENAI_API_KEY"):
    print("WARNING: OPENAI_API_KEY not set. RAG functionality will likely fail.")

# --- Lifespan for resource management ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("FastAPI startup: Initializing resources...")
    # Ledger for /collect endpoint (human dwell time)
    # Using a relative path from where the backend might be run, or an absolute path.
    # For consistency with AEPLedger defaults, let's use its default base path and a specific name.
    # Prod.md example: ledger_human = AEPLedger("data/.aep/human_dwell_events.aep")
    # This implies a specific file, not a ledger name for rotation. AEPLedger expects a dir & name.
    # Let's assume data/.aep/ is relative to aep-sdk root for now.
    sdk_root_path = Path(__file__).parent.parent
    human_ledger_base = sdk_root_path / "data" / ".aep" # Consistent with prod.md example intent
    app.state.collect_ledger = AEPLedger(ledger_base_path=human_ledger_base, ledger_name="human_dwell_events")
    print(f"Collect ledger initialized: {app.state.collect_ledger.current_ledger_file}")

    # Ledger and Callback Handler for RAG LLM events
    rag_llm_ledger_base = sdk_root_path / "data" / ".aep"
    app.state.rag_llm_ledger = AEPLedger(ledger_base_path=rag_llm_ledger_base, ledger_name="rag_llm_events")
    app.state.aep_rag_callback_handler = AEPCallbackHandler(ledger=app.state.rag_llm_ledger)
    print(f"RAG LLM ledger initialized: {app.state.rag_llm_ledger.current_ledger_file}")

    # RAG Graph Initialization
    # The run-book example: rag_graph = get_initialized_rag_graph(ledger_llm)
    # My get_initialized_rag_graph doesn't take a ledger for LLM events directly,
    # it uses a global llm and the callback handler is passed during .invoke().
    # The important part is that the docs are loaded.
    print("Initializing RAG graph...")
    # Ensure docs path is correct, relative to aep-sdk root
    docs_path_for_rag = sdk_root_path / "docs" 
    if not docs_path_for_rag.exists() or not list(docs_path_for_rag.glob("**/*.md*x")):
        print(f"WARNING: RAG documents directory '{docs_path_for_rag}' is empty or missing.")
        docs_path_for_rag.mkdir(parents=True, exist_ok=True)
        with open(docs_path_for_rag / "_placeholder.md", "w") as f:
            f.write("# Placeholder Document\nFor RAG initialization.")
        print(f"Created a placeholder document in {docs_path_for_rag}")
    app.state.rag_graph_instance = get_initialized_rag_graph(docs_path_str=str(docs_path_for_rag))
    print("RAG graph initialized.")
    
    yield
    
    print("FastAPI shutdown: Cleaning up resources...")
    # AEPLedger doesn't have an explicit close() method for file handles as it opens/closes on append.
    # If it did, e.g., for flushing a buffer or closing a continuously open file, it would be called here.
    # print(f"Closing collect ledger: {app.state.collect_ledger.current_ledger_file}")
    # app.state.collect_ledger.close() # If AEPLedger had a close()
    # print(f"Closing RAG LLM ledger: {app.state.rag_llm_ledger.current_ledger_file}")
    # app.state.rag_llm_ledger.close() # If AEPLedger had a close()
    print("Ledger cleanup (if any) handled by AEPLedger's append/rotate logic.")

# --- Application Setup ---
app = FastAPI(
    title="AEP Collector and RAG API",
    version="0.1.0",
    lifespan=lifespan
)

# --- Models ---
class CollectAEPPayload(BaseModel):
    doc_source: str = Field(..., description="Source identifier for the document, e.g., path or URL.")

class HumanDwellEventRequest(BaseModel):
    focus_ms: int = Field(..., ge=0, description="Dwell time in milliseconds.")
    payload: CollectAEPPayload
    focus_kind: str = Field("human_dwell", pattern="^human_dwell$", description="Type of focus event.")
    session_id: str = Field(..., description="Unique session identifier.")

class RAGQueryRequest(BaseModel):
    question: str
    # session_id: Optional[str] = None # Could be used for session-specific context later

class RAGQueryResponse(BaseModel):
    query_id: str
    question: str
    answer: str
    # context: Optional[List[Dict[str, Any]]] = None # Optionally return context sources

# --- Endpoints ---
@app.post("/collect", status_code=202)
async def collect_aep_event(event_data: HumanDwellEventRequest = Body(...), app_state: FastAPI = Depends(lambda: app)):
    current_ts = time.time()
    id_source_str = f"{event_data.payload.doc_source}{event_data.session_id}"
    event_id = hashlib.sha256(id_source_str.encode('utf-8')).hexdigest()

    ledger_event = {
        "id": event_id,
        "ts": current_ts,
        "focus_ms": event_data.focus_ms,
        "payload": event_data.payload.dict(),
        "focus_kind": event_data.focus_kind,
        "session_id": event_data.session_id
    }
    try:
        app.state.collect_ledger.append(ledger_event) # Use ledger from app.state
        return {"message": "AEP event accepted", "event_id": event_id, "timestamp": current_ts}
    except Exception as e:
        print(f"Error writing to collect_ledger: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record AEP event: {str(e)}")

@app.post("/rag/query", response_model=RAGQueryResponse)
async def query_rag_endpoint(request_data: RAGQueryRequest = Body(...), app_state: FastAPI = Depends(lambda: app)):
    if not hasattr(app.state, 'rag_graph_instance') or app.state.rag_graph_instance is None:
        print("Error: RAG graph not initialized. Please wait or check server logs.")
        raise HTTPException(status_code=503, detail="RAG service not yet available.")

    query_id = f"rag_query_{uuid.uuid4()}"
    
    invocation_config = {
        "callbacks": [app.state.aep_rag_callback_handler], # Use handler from app.state
        "metadata": {"query_id": query_id}
    }
    
    initial_rag_state: RAGState = {
        "question": request_data.question,
        "query_id": query_id,
        "context": [], 
        "answer": ""
    }

    try:
        if not os.environ.get("OPENAI_API_KEY"):
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured on server.")
        
        result_state = app.state.rag_graph_instance.invoke(initial_rag_state, config=invocation_config)
        answer = result_state.get("answer", "No answer generated.")
        if not answer:
             answer = "The RAG chain could not generate an answer for this query."

        return RAGQueryResponse(
            query_id=query_id,
            question=request_data.question,
            answer=answer
        )
    except Exception as e:
        print(f"Error during RAG query processing: {e}")
        # Consider more specific error handling based on exception types
        raise HTTPException(status_code=500, detail=f"Error processing RAG query: {str(e)}")

@app.get("/")
async def read_root():
    return {"message": "AEP SDK Backend is running. Use /docs for API details."}

# To run for development: poetry run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
if __name__ == "__main__":
    # This is for direct execution `python backend/main.py` which isn't typical for poetry projects.
    # Poetry run command above is preferred.
    print("To run this FastAPI application:")
    print("1. Ensure 'aep' package and dependencies are installed (e.g., `poetry install`)")
    print("2. Run with Uvicorn: `poetry run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000`")
    print("3. Ensure OPENAI_API_KEY is set in your environment.")
    print("4. Ensure aep-sdk/docs directory exists and contains markdown files for RAG context.") 