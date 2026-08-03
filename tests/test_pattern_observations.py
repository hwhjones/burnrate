import json
import tempfile
import unittest
from pathlib import Path

from burnrate.analyser.patterns import PatternReader, detect_observations


class PatternObservationTests(unittest.TestCase):
    def write_records(self, directory: Path, records: list[dict]) -> Path:
        path = directory / "session.jsonl"
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
        return path

    def test_repeated_reads_count_n_minus_one_per_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self.write_records(Path(temp_dir), [
                {"session_id": "a", "payload": {"type": "read_file", "path": "src/app.py"}},
                {"session_id": "a", "payload": {"type": "read_file", "path": "src\\app.py"}},
                {"session_id": "a", "payload": {"type": "read_file", "path": "src/app.py"}},
                {"session_id": "b", "payload": {"type": "read_file", "path": "src/app.py"}},
            ])
            results = detect_observations(PatternReader(str(path)).scan())
            self.assertEqual(results[0]["id"], "R-READ-01")
            self.assertEqual(results[0]["count"], 2)
            self.assertEqual(results[0]["affected_sessions"], 1)

    def test_retries_are_consecutive_and_change_or_success_ends_sequence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self.write_records(Path(temp_dir), [
                {"session_id": "a", "payload": {"type": "command_execution", "command": "make test", "exit_code": 1, "error": "missing"}},
                {"session_id": "a", "payload": {"type": "command_execution", "command": "make test", "exit_code": 1, "error": "missing"}},
                {"session_id": "a", "payload": {"type": "command_execution", "command": "make test", "exit_code": 0}},
                {"session_id": "a", "payload": {"type": "command_execution", "command": "make test", "exit_code": 1, "error": "missing"}},
                {"session_id": "a", "payload": {"type": "command_execution", "command": "make test", "exit_code": 1, "error": "changed"}},
            ])
            results = detect_observations(PatternReader(str(path)).scan())
            self.assertEqual(results[0]["id"], "R-RETRY-01")
            self.assertEqual(results[0]["count"], 1)

    def test_test_churn_ends_at_successful_mutation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self.write_records(Path(temp_dir), [
                {"session_id": "a", "payload": {"type": "command_execution", "command": "pytest tests/test_app.py", "exit_code": 1, "error": "failed"}},
                {"session_id": "a", "payload": {"type": "command_execution", "command": "pytest tests/test_app.py", "exit_code": 1, "error": "failed"}},
                {"session_id": "a", "payload": {"type": "command_execution", "command": "apply_patch", "exit_code": 0, "success": True}},
                {"session_id": "a", "payload": {"type": "command_execution", "command": "pytest tests/test_app.py", "exit_code": 1, "error": "failed"}},
            ])
            results = detect_observations(PatternReader(str(path)).scan())
            self.assertEqual(results[0]["id"], "R-TEST-01")
            self.assertEqual(results[0]["count"], 1)

    def test_real_codex_function_call_envelope_produces_read_fact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self.write_records(Path(temp_dir), [
                {"type": "response_item", "session_id": "a", "payload": {"type": "function_call", "name": "shell_command", "call_id": "1", "arguments": json.dumps({"command": "Get-Content -LiteralPath 'src/app.py'"})}},
                {"type": "response_item", "session_id": "a", "payload": {"type": "function_call_output", "call_id": "1", "output": "Exit code: 0"}},
                {"type": "response_item", "session_id": "a", "payload": {"type": "function_call", "name": "shell_command", "call_id": "2", "arguments": json.dumps({"command": "Get-Content -LiteralPath 'src/app.py'"})}},
                {"type": "response_item", "session_id": "a", "payload": {"type": "function_call_output", "call_id": "2", "output": "Exit code: 0"}},
            ])
            results = detect_observations(PatternReader(str(path)).scan())
            self.assertEqual(results[0]["id"], "R-READ-01")
            self.assertEqual(results[0]["count"], 1)
    def test_missing_required_fields_suppress_rules_and_examples_are_bounded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            records = [{"session_id": "a", "payload": {"type": "read_file"}}]
            records.extend({"session_id": "a", "payload": {"type": "read_file", "path": "file.py"}} for _ in range(5))
            path = self.write_records(Path(temp_dir), records)
            results = detect_observations(PatternReader(str(path)).scan())
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["id"], "R-READ-01")
            self.assertEqual(len(results[0]["examples"]), 3)


if __name__ == "__main__":
    unittest.main()