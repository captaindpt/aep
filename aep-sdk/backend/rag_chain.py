import os
import time
import hashlib
import json
from pathlib import Path
from typing import List, TypedDict, Optional, Any, Dict
from uuid import uuid4

from langchain import hub
from langchain_community.document_loaders import TextLoader, DirectoryLoader
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
# DocArrayInMemorySearch was used in PoC, FAISS is in prod.md. Let's use FAISS.
# from langchain_community.vectorstores import DocArrayInMemorySearch 
from langchain_community.vectorstores import FAISS
from langgraph.graph.state import START
from langgraph.graph import END, StateGraph

from aep.callback import AEPCallbackHandler # Corrected import path

# Default path for documents, relative to the aep-sdk directory
# This should be configurable in a real application.
DEFAULT_DOCS_PATH = Path(__file__).parent.parent / "docs"
DEFAULT_RETRIEVAL_LOG_PATH = Path(__file__).parent.parent / "data" / "retrieval_log.jsonl"

# Ensure OPENAI_API_KEY is set (can be moved to a config module later)
if not os.environ.get("OPENAI_API_KEY"):
    print("OPENAI_API_KEY not set. Please set it as an environment variable.")
    # Not exiting here, but RAG will fail if not set.

# --- LangChain Components ---
# These could be initialized with config values in a more complex app
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
embeddings_model = OpenAIEmbeddings(model="text-embedding-3-large")
rag_prompt = hub.pull("rlm/rag-prompt")

# Global variable for vector_store, to be initialized by load_and_index_docs
# This is a simple way to manage it for this module; a class might be better for complex state.
vector_store: Optional[FAISS] = None
RETRIEVER_K = 15  # Increased K for initial retrieval
FILTER_TOP_N = 3   # Number of documents to keep after filtering

def load_and_index_docs(docs_path: Path = DEFAULT_DOCS_PATH, force_reindex: bool = False) -> FAISS:
    """
    Loads documents from the specified path, splits them, embeds them, 
    and creates a FAISS vector store.

    Args:
        docs_path: Path to the directory containing .md and .mdx files.
        force_reindex: If True, re-index even if a FAISS index already exists (not implemented yet).
                       Currently, it always re-indexes on call.

    Returns:
        A FAISS vector store instance.
    """
    global vector_store # Allow modification of the global vector_store

    print(f"Loading documents from: {docs_path}")
    mdx_loader = DirectoryLoader(
        path=str(docs_path),
        glob="**/*.mdx",
        loader_cls=TextLoader,
        show_progress=True,
        use_multithreading=True,
        silent_errors=True
    )
    md_loader = DirectoryLoader(
        path=str(docs_path),
        glob="**/*.md",
        loader_cls=TextLoader,
        show_progress=True,
        use_multithreading=True,
        silent_errors=True
    )
    
    loaded_docs = mdx_loader.load() + md_loader.load()

    if not loaded_docs:
        print(f"Warning: No documents found in {docs_path}. RAG will have no context.")
        # Create an empty FAISS index if no docs, to prevent errors downstream
        # FAISS.from_texts requires at least one text.
        vector_store = FAISS.from_texts(
            texts=["EMPTY_PLACEHOLDER_FOR_INITIALIZATION"], 
            embedding=embeddings_model,
            metadatas=[{"source": "dummy"}]
        )
        return vector_store

    print(f"Loaded {len(loaded_docs)} total documents.")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    all_splits = text_splitter.split_documents(loaded_docs)
    print(f"Created {len(all_splits)} document splits.")

    if not all_splits:
        print("Warning: No splits created from documents. RAG will have no context.")
        vector_store = FAISS.from_texts(
            texts=["EMPTY_PLACEHOLDER_FOR_INITIALIZATION"], 
            embedding=embeddings_model,
            metadatas=[{"source": "dummy"}] 
        )
        return vector_store

    print("Indexing document splits with FAISS...")
    # TODO: Implement persistence for FAISS index to avoid re-indexing every time.
    # For now, we re-index in memory on each call to load_and_index_docs.
    # faiss_index_path = docs_path.parent / "faiss_index"
    # if force_reindex or not faiss_index_path.exists():
    #     vector_store = FAISS.from_documents(documents=all_splits, embedding=embeddings_model)
    #     vector_store.save_local(str(faiss_index_path))
    # else:
    #     vector_store = FAISS.load_local(str(faiss_index_path), embeddings_model, allow_dangerous_deserialization=True)
    vector_store = FAISS.from_documents(documents=all_splits, embedding=embeddings_model)
    print("FAISS indexing complete.")
    return vector_store

# --- LangGraph State and Nodes ---
class RAGState(TypedDict):
    question: str
    context: List[Document] # This will hold the *final* context for the LLM
    answer: str
    query_id: Optional[str] # To carry query_id through the graph
    raw_retrieved_docs_with_scores: Optional[List[tuple[Document, float]]] # For intermediate storage
    # Add aep_handler for graph-specific callbacks if needed, or rely on global config

def retrieve_documents(state: RAGState):
    """
    Retrieves documents from the vector store based on the question.
    Also logs retrieval information.
    """
    global vector_store
    if vector_store is None:
        # This can happen if load_and_index_docs was not called or failed.
        # Or if the global wasn't set correctly in a multi-threaded/process env (not an issue here yet)
        print("Error: Vector store not initialized. Call load_and_index_docs first.")
        # Fallback to empty context to prevent downstream errors, or raise an exception.
        return {"context": [], "query_id": state.get("query_id")} 

    question = state["question"]
    query_id = state.get("query_id") # Get query_id from input state, should be set by caller
    
    # If query_id isn't passed, generate one. This is important for linking.
    if not query_id:
        query_id = f"rag_query_{uuid4()}"
        print(f"Warning: query_id not provided to RAG graph, generated: {query_id}")

    # Retrieve more documents initially
    retrieved_docs_with_scores = vector_store.similarity_search_with_score(question, k=RETRIEVER_K)
    
    # Normalize doc_source to be relative to docs root so it matches golden paths
    retrieved_items = []
    for doc, score in retrieved_docs_with_scores:
        raw_source = doc.metadata.get("source", "unknown_source_in_item")
        try:
            rel_path = str(Path(raw_source).relative_to(DEFAULT_DOCS_PATH))
            if rel_path.startswith("docs/"):
                rel_path = rel_path[len("docs/"):]  # remove leading docs/ to align with golden paths
        except ValueError:
            # If not under docs path, fall back to basename
            rel_path = Path(raw_source).name
        retrieved_items.append({"doc_source": rel_path, "score": float(score)})

    # Prepare data for retrieval_log.jsonl
    log_entry = {
        "ts": time.time(),
        "query_id": query_id,
        "question": question,
        "retrieved_items": retrieved_items,
    }
    
    # Ensure data directory exists for retrieval log
    retrieval_log_file = Path(DEFAULT_RETRIEVAL_LOG_PATH)
    retrieval_log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(retrieval_log_file, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    # Store the raw retrieved docs with scores in the state for the filter node
    # The 'context' field will be populated by the filter node later.
    return {"raw_retrieved_docs_with_scores": retrieved_docs_with_scores, "query_id": query_id, "question": question}

def filter_top_n_documents(state: RAGState):
    """Filters the raw retrieved documents to the top N based on score (or simple truncation if no scores)."""
    raw_docs_with_scores = state.get("raw_retrieved_docs_with_scores")
    query_id = state.get("query_id")
    question = state.get("question") # Keep question in state

    if not raw_docs_with_scores:
        print(f"Warning (QID: {query_id}): No raw documents to filter. Context will be empty.")
        return {"context": [], "query_id": query_id, "question": question}

    # FAISS similarity_search_with_score returns (Document, float_score)
    # Lower scores are better (distances). So we sort by score ascending.
    # If it were cosine similarity (higher is better), we'd sort descending.
    # For FAISS, scores are L2 distances, so lower is better.
    
    # Sort by score (ascending, as lower L2 distance is better for FAISS)
    # If in the future a different vector store is used that provides similarity (higher is better),
    # this sorting logic would need to be adjusted or made more generic.
    sorted_docs_with_scores = sorted(raw_docs_with_scores, key=lambda x: x[1])
    
    top_n_docs = [doc for doc, score in sorted_docs_with_scores[:FILTER_TOP_N]]
    
    if not top_n_docs:
        print(f"Warning (QID: {query_id}): Filtered context is empty after selecting top {FILTER_TOP_N}.")

    # For AEP, the 'context' that matters is what the LLM sees.
    # So, this node now sets the 'context' field for the 'generate_answer' node.
    print(f"DEBUG (QID: {query_id}): Raw retrieval count: {len(raw_docs_with_scores)}, Filtered to: {len(top_n_docs)} for LLM.")
    return {"context": top_n_docs, "query_id": query_id, "question": question}

def generate_answer(state: RAGState):
    """Generates an answer using the LLM based on the question and retrieved context."""
    docs_content = "\n\n".join(doc.page_content for doc in state["context"])
    messages = rag_prompt.invoke({"question": state["question"], "context": docs_content})
    
    # The AEPCallbackHandler will pick up query_id from the config's metadata if it's passed correctly
    # when graph.invoke is called.
    response = llm.invoke(messages)
    return {"answer": response.content, "query_id": state.get("query_id")} # Pass query_id along

# --- RAG Graph Construction --- 
def create_rag_graph() -> StateGraph:
    """
    Creates and compiles the LangGraph RAG chain.
    Vector store must be initialized by calling load_and_index_docs() before invoking the graph.
    """
    graph_builder = StateGraph(RAGState)
    graph_builder.add_node("retrieve", retrieve_documents)
    graph_builder.add_node("filter_documents", filter_top_n_documents) # New filter node
    graph_builder.add_node("generate", generate_answer)
    
    graph_builder.add_edge(START, "retrieve")
    graph_builder.add_edge("retrieve", "filter_documents") # retrieve -> filter
    graph_builder.add_edge("filter_documents", "generate")   # filter -> generate
    graph_builder.add_edge("generate", END)
    
    rag_graph = graph_builder.compile()
    return rag_graph

# --- Main function to get an initialized RAG graph ---
# This is what the FastAPI backend will typically use.
def get_initialized_rag_graph(docs_path_str: Optional[str] = None, force_reindex_docs: bool = False) -> StateGraph:
    """
    Initializes the document vector store and returns the compiled RAG graph.
    This is a convenience function to ensure docs are loaded before graph is used.

    Args:
        docs_path_str: Optional path to the documents directory. 
                       Defaults to DEFAULT_DOCS_PATH set in this module.
        force_reindex_docs: Whether to force re-indexing of documents.

    Returns:
        The compiled RAG StateGraph.
    """
    doc_path = Path(docs_path_str) if docs_path_str else DEFAULT_DOCS_PATH
    
    global vector_store
    if vector_store is None or force_reindex_docs:
         # Load and index documents, this sets the global vector_store
        print(f"Initializing vector store... Docs path: {doc_path}, Force reindex: {force_reindex_docs}")
        load_and_index_docs(docs_path=doc_path, force_reindex=force_reindex_docs)
    else:
        print("Using existing in-memory vector store.")
        
    return create_rag_graph()


if __name__ == "__main__":
    # Example of using the RAG chain directly from this module for testing.
    print("--- Testing RAG Chain directly (not via FastAPI) ---")
    
    # 1. Initialize and get the graph
    #    (This will load docs from aep-sdk/docs/ by default)
    #    Ensure you have some .md or .mdx files in aep-sdk/docs/
    #    For example, copy them from the PoC: cp -r ../../aep-demo/docs/ ../docs/
    if not DEFAULT_DOCS_PATH.exists() or not list(DEFAULT_DOCS_PATH.glob("**/*.md*x")):
        print(f"WARNING: Default docs path {DEFAULT_DOCS_PATH} is empty or missing markdown files.")
        print("Please populate it for the RAG chain to have context (e.g., copy from PoC's aep-demo/docs/)")
        # Create dummy docs dir if it doesn't exist to avoid load_and_index_docs erroring on path not found
        DEFAULT_DOCS_PATH.mkdir(parents=True, exist_ok=True)
        # Fallback: create a dummy file so FAISS init doesn't fail, RAG will be weak.
        with open(DEFAULT_DOCS_PATH / "dummy_doc.md", "w") as f:
            f.write("# Dummy Document\nThis is a dummy document for initialization purposes.")
        print(f"Created a dummy document in {DEFAULT_DOCS_PATH}")

    rag_app = get_initialized_rag_graph()
    
    # 2. Setup AEP Callback for this test run
    #    The AEP SDK callback handler expects an AEPLedger instance.
    from aep.ledger import AEPLedger
    test_rag_ledger = AEPLedger(ledger_name="test_rag_chain_direct") # Separate ledger for this test
    aep_rag_test_handler = AEPCallbackHandler(ledger=test_rag_ledger)
    
    test_questions = [
        "What is LangChain?",
        "Explain the concept of a LangChain Agent.",
    ]

    print(f"\n--- Running {len(test_questions)} test queries ---")
    for i, question_text in enumerate(test_questions):
        print(f"\nQuery {i+1}: {question_text}")
        start_q_time = time.time()
        
        # Generate a query_id for this specific invocation for linking
        current_query_id = f"test_direct_{uuid4()}"
        
        # To pass query_id to AEPCallbackHandler, it needs to be in invoke's config metadata
        # The RAG graph (retrieve_documents) will also pick it up from the state.
        invocation_config = {
            "callbacks": [aep_rag_test_handler],
            "metadata": {"query_id": current_query_id} 
        }
        
        try:
            # The input to the graph is the initial state, ensure query_id is there too for retrieve_documents
            response_data = rag_app.invoke(
                {"question": question_text, "query_id": current_query_id, "raw_retrieved_docs_with_scores": []}, # Add new state field
                config=invocation_config
            )
            answer_text = response_data.get('answer', "No answer found.")
            print(f"Answer: {answer_text}")
        except Exception as e_test:
            print(f"Error processing question '{question_text}': {e_test}")
        
        end_q_time = time.time()
        print(f"Time taken for query {i+1}: {end_q_time - start_q_time:.2f}s")
        if i < len(test_questions) - 1:
            time.sleep(0.5) 

    print(f"\n--- Test queries finished --- ")
    print(f"AEP events for this test run logged to ledger: {test_rag_ledger.ledger_name}")
    print(f"Inspect with: poetry run aep inspect --ledger-name {test_rag_ledger.ledger_name}")
    print(f"Retrieval logs for this test run logged to: {DEFAULT_RETRIEVAL_LOG_PATH}") 