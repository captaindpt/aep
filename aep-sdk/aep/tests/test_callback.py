import unittest
from unittest.mock import MagicMock, patch, ANY
import time
import hashlib
import msgpack
from uuid import uuid4
from pathlib import Path

from langchain_core.outputs import LLMResult, Generation

from aep.callback import AEPCallbackHandler
from aep.ledger import AEPLedger # For type hinting and potentially default instantiation

class TestAEPCallbackHandler(unittest.TestCase):

    def setUp(self):
        self.mock_ledger = MagicMock(spec=AEPLedger)
        # For testing default ledger instantiation
        self.test_dir = Path(unittest.TestCase.gettmpdir(self)) / "test_aep_callback_default_ledger"
        self.test_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        # Clean up the temporary directory for default ledger if created
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_01_initialization_with_mock_ledger(self):
        handler = AEPCallbackHandler(ledger=self.mock_ledger)
        self.assertIsNotNone(handler.ledger)
        self.assertIs(handler.ledger, self.mock_ledger)

    def test_02_initialization_with_default_ledger(self):
        # Patch AEPLedger constructor to verify it's called with default args
        with patch('aep.callback.AEPLedger') as MockAEPLedgerConstructor:
            mock_default_ledger_instance = MockAEPLedgerConstructor.return_value
            handler = AEPCallbackHandler(ledger=None)
            self.assertIsNotNone(handler.ledger)
            MockAEPLedgerConstructor.assert_called_once_with() # Called with no args for defaults
            self.assertIs(handler.ledger, mock_default_ledger_instance)

    def test_03_on_llm_start(self):
        handler = AEPCallbackHandler(ledger=self.mock_ledger)
        test_run_id = uuid4()
        test_query_id = "query_123"
        metadata = {"query_id": test_query_id, "other_meta": "value"}
        
        self.assertIsNone(handler._start_time)
        self.assertIsNone(handler._current_query_id)
        self.assertIsNone(handler._current_metadata)

        handler.on_llm_start({}, [], run_id=test_run_id, metadata=metadata)
        
        self.assertIsNotNone(handler._start_time)
        self.assertAlmostEqual(handler._start_time, time.time(), delta=0.1)
        self.assertEqual(handler._current_query_id, test_query_id)
        self.assertEqual(handler._current_metadata, metadata)

    def test_04_on_llm_start_no_query_id(self):
        handler = AEPCallbackHandler(ledger=self.mock_ledger)
        test_run_id = uuid4()
        metadata_no_query_id = {"other_meta": "value"}
        handler.on_llm_start({}, [], run_id=test_run_id, metadata=metadata_no_query_id)
        self.assertIsNone(handler._current_query_id)
        self.assertEqual(handler._current_metadata, metadata_no_query_id)

        handler.on_llm_start({}, [], run_id=test_run_id, metadata=None)
        self.assertIsNone(handler._current_query_id)
        self.assertIsNone(handler._current_metadata)

    def test_05_on_llm_end_event_structure(self):
        handler = AEPCallbackHandler(ledger=self.mock_ledger)
        test_run_id = uuid4()
        test_query_id = "q_abc"
        start_time_sim = time.time() - 0.5 # Simulate 500ms ago
        
        handler._start_time = start_time_sim
        handler._current_query_id = test_query_id
        handler._current_metadata = {"query_id": test_query_id}

        mock_generation = MagicMock(spec=Generation)
        mock_generation.text = "Test LLM response content."
        mock_llm_result = MagicMock(spec=LLMResult)
        mock_llm_result.generations = [[mock_generation]]
        
        handler.on_llm_end(mock_llm_result, run_id=test_run_id)

        self.mock_ledger.append.assert_called_once()
        call_args = self.mock_ledger.append.call_args[0][0]
        
        self.assertIn("id", call_args)
        self.assertIn("ts", call_args)
        self.assertIn("focus_ms", call_args)
        self.assertIn("payload", call_args)
        self.assertIn("focus_kind", call_args)
        self.assertIn("query_id", call_args)

        self.assertEqual(call_args["focus_kind"], "exec_latency")
        self.assertEqual(call_args["query_id"], test_query_id)
        self.assertIsInstance(call_args["focus_ms"], int)
        self.assertGreaterEqual(call_args["focus_ms"], 490) # accounting for small delta
        self.assertLessEqual(call_args["focus_ms"], 600)    # and slight variations
        
        expected_payload = {"role": "assistant", "content": mock_generation.text}
        self.assertEqual(call_args["payload"], expected_payload)
        
        expected_id_source = msgpack.packb(expected_payload)
        expected_id = hashlib.sha256(expected_id_source).hexdigest()
        self.assertEqual(call_args["id"], expected_id)
        
        self.assertAlmostEqual(call_args["ts"], time.time(), delta=0.1)

        # Check state reset
        self.assertIsNone(handler._start_time)
        self.assertIsNone(handler._current_query_id)
        self.assertIsNone(handler._current_metadata)

    def test_06_on_llm_end_no_generations(self):
        handler = AEPCallbackHandler(ledger=self.mock_ledger)
        handler._start_time = time.time() - 0.1
        mock_llm_result_no_gen = MagicMock(spec=LLMResult)
        mock_llm_result_no_gen.generations = [] # No generations
        
        handler.on_llm_end(mock_llm_result_no_gen, run_id=uuid4())
        self.mock_ledger.append.assert_not_called()
        # State should still be reset
        self.assertIsNone(handler._start_time)

    def test_07_on_llm_end_start_time_none(self):
        handler = AEPCallbackHandler(ledger=self.mock_ledger)
        handler._start_time = None # Ensure start time is None
        mock_llm_result = MagicMock(spec=LLMResult)
        mock_llm_result.generations = [[MagicMock(spec=Generation, text="test")]]

        handler.on_llm_end(mock_llm_result, run_id=uuid4())
        self.mock_ledger.append.assert_not_called()

    def test_08_on_llm_error(self):
        handler = AEPCallbackHandler(ledger=self.mock_ledger)
        handler._start_time = time.time()
        handler._current_query_id = "q_err"
        handler._current_metadata = {"query_id": "q_err"}

        handler.on_llm_error(Exception("test error"), run_id=uuid4())
        
        self.assertIsNone(handler._start_time)
        self.assertIsNone(handler._current_query_id)
        self.assertIsNone(handler._current_metadata)
        self.mock_ledger.append.assert_not_called() # No event logged on error

if __name__ == '__main__':
    unittest.main()
