import time
import hashlib
import msgpack
# import os # No longer directly needed for path manipulation here
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.outputs import LLMResult, ChatGenerationChunk, GenerationChunk
from langchain_core.documents import Document # Added for typing

from .ledger import AEPLedger # Import the new AEPLedger class

# DEFAULT_AEP_DIR and DEFAULT_LEDGER_FILE are now managed by AEPLedger
# or passed to it. Not directly needed here if ledger is injected.

class AEPCallbackHandler(BaseCallbackHandler):
    """
    A LangChain callback handler to log LLM interaction events (AEPs)
    using an AEPLedger instance.
    """

    def __init__(self, ledger: Optional[AEPLedger] = None):
        """
        Initializes the callback handler.

        Args:
            ledger: An instance of AEPLedger to use for storing events.
                    If None, a default AEPLedger will be instantiated.
        """
        if ledger is None:
            self.ledger = AEPLedger() # Use default AEPLedger settings
        else:
            self.ledger = ledger
        
        self._start_time: Optional[float] = None
        self._current_query_id: Optional[str] = None
        self._current_metadata: Optional[Dict[str, Any]] = None
        self._current_run_id_stack: List[UUID] = [] # To track chain hierarchy

    # Helper method to safely process inputs/outputs for logging
    def _process_io_for_logging(self, io_data: Any) -> Any:
        if isinstance(io_data, dict):
            processed_dict = {}
            for key, value in io_data.items():
                if key == "raw_retrieved_docs_with_scores" and isinstance(value, list):
                    processed_list = []
                    for item in value:
                        if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], Document):
                            doc_summary = {"page_content_summary": item[0].page_content[:200] + "...", "metadata": item[0].metadata}
                            score = item[1]
                            # Convert numpy.float32 to standard Python float
                            if hasattr(score, 'item'): # Check if it's a numpy type with .item()
                                try:
                                    score = score.item()
                                except AttributeError:
                                    pass # It might not be a numpy scalar, or .item() not suitable
                            elif isinstance(score, (float, int)): # Already a Python native numeric type
                                pass
                            else: # Attempt generic float conversion as a fallback for other numeric types
                                try:
                                    score = float(score)
                                except (ValueError, TypeError):
                                    score = str(score) # If cannot convert to float, keep as string representation

                            processed_list.append((doc_summary, score))
                        else:
                            processed_list.append(item) # Keep other tuple forms or non-Document tuples as is
                    processed_dict[key] = processed_list
                elif isinstance(value, list) and all(isinstance(doc, Document) for doc in value):
                    processed_dict[key] = [{"page_content_summary": doc.page_content[:200] + "...", "metadata": doc.metadata} for doc in value]
                elif isinstance(value, Document):
                    processed_dict[key] = {"page_content_summary": value.page_content[:200] + "...", "metadata": value.metadata}
                elif hasattr(value, '__dict__'): # For other complex objects, try to get their dict representation
                    try:
                        # Avoid trying to serialize things that are too complex or have no simple dict form
                        if isinstance(value, (ChatGenerationChunk, GenerationChunk, LLMResult)):
                             processed_dict[key] = shorten_serialized(value.__dict__, max_len=500) # Use existing shorten_serialized
                        else:
                            # For other known types like ChatPromptValue, convert to string or a simpler dict
                            # For now, a general approach for objects with __dict__
                            processed_dict[key] = str(value) # Fallback to string if too complex
                    except Exception:
                        processed_dict[key] = f"Unserializable object: {type(value).__name__}"
                else:
                    processed_dict[key] = value
            return processed_dict
        elif isinstance(io_data, list) and all(isinstance(doc, Document) for doc in io_data):
            return [{"page_content_summary": doc.page_content[:200] + "...", "metadata": doc.metadata} for doc in io_data]
        elif isinstance(io_data, Document):
            return {"page_content_summary": io_data.page_content[:200] + "...", "metadata": io_data.metadata}
        
        # Handle ChatPromptValue and other non-dict, non-Document types that might appear in outputs
        if not isinstance(io_data, (dict, list)):
            try:
                # If it's a known Langchain object, try to get a sensible string representation
                if hasattr(io_data, 'to_messages') or hasattr(io_data, 'text') or hasattr(io_data, 'content'):
                    return str(io_data)
                return shorten_serialized(io_data.__dict__ if hasattr(io_data, '__dict__') else io_data, max_len=500)
            except Exception:
                 return f"Unserializable IO object: {type(io_data).__name__}"
        return io_data # Fallback for other types

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Record the start time and capture query_id from metadata."""
        self._start_time = time.time()
        self._current_metadata = metadata
        if metadata and "query_id" in metadata:
            self._current_query_id = str(metadata["query_id"])
        else:
            # Fallback or generate if not provided? For now, None.
            # Or use run_id or parent_run_id as a potential query_id?
            # Let's keep it simple: if not in metadata, it's not logged for now.
            self._current_query_id = None


    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Compute latency and log AEP event to MsgPack file on LLM end."""
        if self._start_time is None:
            # This can happen if on_llm_error is called before on_llm_end,
            # or if on_llm_start was not called.
            return

        end_time = time.time()
        latency_ms = int((end_time - self._start_time) * 1000)

        if response.generations and response.generations[0]:
            # Assuming the first generation from the first response is the primary one
            generation = response.generations[0][0]
            payload_content = generation.text
            
            payload = {"role": "assistant", "content": payload_content}
            
            # Generate ID based on this payload as per prod.md
            # id: "<sha256(payload)>" -> refers to the dict, not just content
            event_id_source = msgpack.packb(payload)
            event_id = hashlib.sha256(event_id_source).hexdigest()

            aep_event: Dict[str, Any] = {
                "id": event_id,
                "ts": end_time,
                "focus_ms": latency_ms,
                "payload": payload,
                "focus_kind": "exec_latency",
            }

            # Add query_id if captured
            if self._current_query_id:
                aep_event["query_id"] = self._current_query_id
            # Potentially add other metadata fields if specified in future
            # e.g. run_id, parent_run_id if they are useful for tracing

            self.ledger.append(aep_event) # Use the ledger instance

        self._start_time = None  # Reset for the next call
        self._current_query_id = None # Reset
        self._current_metadata = None # Reset

    def on_llm_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Clean up start time on LLM error."""
        self._start_time = None
        self._current_query_id = None
        self._current_metadata = None
        # Log the error
        trace_id_to_log = self._current_query_id or str(run_id)
        self.ledger.append({
            "id": hashlib.sha256(msgpack.packb({"error": str(error), "run_id": str(run_id)})).hexdigest(),
            "ts": time.time(),
            "trace_id": trace_id_to_log,
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
            "run_id": str(run_id),
            "event_type": "llm_error",
            "event_source": "llm", # Or serialized.get("name", "unknown_llm")
            "payload": {"error": str(error)},
            "focus_kind": "error"
        })

    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Log chain start event."""
        self._current_run_id_stack.append(run_id)
        # Attempt to get query_id from metadata if it's the start of a root chain call
        current_query_id = None
        if metadata and "query_id" in metadata:
            current_query_id = str(metadata["query_id"])
        elif self._current_query_id: # Inherit from parent if already set (e.g. by LLM call meta)
            current_query_id = self._current_query_id
        else: # Fallback to run_id if no query_id is explicitly passed or inherited
            current_query_id = str(run_id)
        
        # For nested chains, ensure query_id continuity if possible.
        # If this is the first event in a trace, metadata["query_id"] is our trace_id.
        # Otherwise, we use the run_id as a fallback trace_id for this specific event,
        # but ideally, it should be linked to an overarching query_id/trace_id.
        # The `invocation_metadata` in run_aep_eval.py sets `query_id` for the root invoke.

        event_source_name = "Unknown Chain"
        if serialized:
            event_source_name = serialized.get("name", serialized.get("id", ["Unknown Chain"])[-1])

        processed_inputs = self._process_io_for_logging(inputs)

        self.ledger.append({
            "id": hashlib.sha256(msgpack.packb({"inputs": processed_inputs, "run_id": str(run_id)})).hexdigest(),
            "ts": time.time(),
            "trace_id": current_query_id,
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
            "run_id": str(run_id),
            "event_type": "chain_start",
            "event_source": event_source_name, 
            "payload": {"inputs": processed_inputs, "serialized_repr": shorten_serialized(serialized) if serialized else None},
            "tags": tags,
            "metadata": metadata,
            "focus_kind": "chain_execution"
        })

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Log chain end event, including outputs."""
        if self._current_run_id_stack and self._current_run_id_stack[-1] == run_id:
            self._current_run_id_stack.pop()

        # Determine trace_id. If query_id was set in metadata for the root call, it should propagate.
        # If not, use run_id.
        current_query_id = self._current_query_id or str(run_id)
        if self._current_metadata and "query_id" in self._current_metadata:
             current_query_id = str(self._current_metadata["query_id"])


        # Attempt to get the name of the chain from the serialized structure if possible
        # This requires access to `serialized` which is not directly passed to on_chain_end
        # We might need to store it from on_chain_start if we want the exact name.
        # For now, using a placeholder or relying on run_id for correlation.
        # A common pattern is for `outputs` to contain special keys if it's a graph's output.
        
        # Sanitize outputs for logging - Documents can be large
        logged_outputs = self._process_io_for_logging(outputs)


        self.ledger.append({
            "id": hashlib.sha256(msgpack.packb({"outputs": logged_outputs, "run_id": str(run_id)})).hexdigest(),
            "ts": time.time(),
            "trace_id": current_query_id,
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
            "run_id": str(run_id),
            "event_type": "chain_output", # Changed to chain_output to match eval script
            "event_source": "chain", # Placeholder - ideally chain name
            "payload": {"outputs": logged_outputs},
            "focus_kind": "chain_execution_result"
        })
        
        # If this was the root chain call for the query_id, reset current_query_id
        if not self._current_run_id_stack and self._current_query_id == current_query_id :
            self._current_query_id = None 
            self._current_metadata = None


    def on_chain_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Log chain error."""
        if self._current_run_id_stack and self._current_run_id_stack[-1] == run_id:
            self._current_run_id_stack.pop()
        
        current_query_id = self._current_query_id or str(run_id)
        if self._current_metadata and "query_id" in self._current_metadata:
             current_query_id = str(self._current_metadata["query_id"])

        self.ledger.append({
            "id": hashlib.sha256(msgpack.packb({"error": str(error), "run_id": str(run_id)})).hexdigest(),
            "ts": time.time(),
            "trace_id": current_query_id,
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
            "run_id": str(run_id),
            "event_type": "chain_error",
            "event_source": "chain", # Placeholder
            "payload": {"error": str(error)},
            "focus_kind": "error"
        })
        if not self._current_run_id_stack and self._current_query_id == current_query_id :
            self._current_query_id = None
            self._current_metadata = None


    def on_retriever_start(
        self,
        serialized: Dict[str, Any],
        query: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Log retriever start event."""
        current_query_id = self._current_query_id or str(parent_run_id or run_id) # Try to link to broader trace
        if self._current_metadata and "query_id" in self._current_metadata:
             current_query_id = str(self._current_metadata["query_id"])


        event_source_name = "Unknown Retriever"
        if serialized:
            event_source_name = serialized.get("name", serialized.get("id", ["Unknown Retriever"])[-1])

        self.ledger.append({
            "id": hashlib.sha256(msgpack.packb({"query": query, "run_id": str(run_id)})).hexdigest(),
            "ts": time.time(),
            "trace_id": current_query_id,
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
            "run_id": str(run_id),
            "event_type": "retriever_start",
            "event_source": event_source_name,
            "payload": {"query": query, "serialized_repr": shorten_serialized(serialized) if serialized else None},
            "tags": tags,
            "metadata": metadata,
            "focus_kind": "retrieval"
        })

    def on_retriever_end(
        self,
        documents: List[Document],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Log retriever end event, including retrieved documents (summarized)."""
        current_query_id = self._current_query_id or str(parent_run_id or run_id)
        if self._current_metadata and "query_id" in self._current_metadata:
             current_query_id = str(self._current_metadata["query_id"])

        logged_documents = [{"page_content_summary": doc.page_content[:200] + "...", "metadata": doc.metadata} for doc in documents]

        self.ledger.append({
            "id": hashlib.sha256(msgpack.packb({"documents_count": len(documents), "run_id": str(run_id)})).hexdigest(), # Avoid hashing full docs
            "ts": time.time(),
            "trace_id": current_query_id,
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
            "run_id": str(run_id),
            "event_type": "retriever_end",
            "event_source": "retriever", # Placeholder - ideally retriever name
            "payload": {"documents": logged_documents, "retrieved_count": len(documents)},
            "focus_kind": "retrieval_result"
        })

# Helper function to shorten serialized representation if it's too long
def shorten_serialized(serialized_obj: Dict[str, Any], max_len: int = 500) -> Dict[str, Any]:
    try:
        s = str(serialized_obj)
        if len(s) > max_len:
            return {"summary": f"Serialized object too long, starts with: {s[:max_len]}..."}
        return serialized_obj
    except Exception:
        return {"summary": "Could not serialize object for summary."}

    # The __exit__ method is not standard for BaseCallbackHandler.
    # If AEPLedger handles resource management (e.g., file handles),
    # this callback won't need it. 