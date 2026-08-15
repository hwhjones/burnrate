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

    def test_repeated_reads_require_three_reads_per_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self.write_records(Path(temp_dir), [
                {"session_id": "a", "payload": {"type": "read_file", "path": "src/app.py"}},
                {"session_id": "a", "payload": {"type": "read_file", "path": "src\\app.py"}},
                {"session_id": "a", "payload": {"type": "read_file", "path": "src/app.py"}},
                {"session_id": "b", "payload": {"type": "read_file", "path": "src/app.py"}},
            ])
            results = detect_observations(PatternReader(str(path)).scan())
            self.assertEqual(results[0]["id"], "R-READ-01")
            self.assertEqual(results[0]["count"], 1)
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
                {"type": "response_item", "session_id": "a", "payload": {"type": "function_call", "name": "shell_command", "call_id": "3", "arguments": json.dumps({"command": "Get-Content -LiteralPath 'src/app.py'"})}},
                {"type": "response_item", "session_id": "a", "payload": {"type": "function_call_output", "call_id": "3", "output": "Exit code: 0"}},
            ])
            results = detect_observations(PatternReader(str(path)).scan())
            self.assertEqual(results[0]["id"], "R-READ-01")
            self.assertEqual(results[0]["count"], 1)
    def test_failed_function_calls_pair_by_session_and_support_structured_envelopes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self.write_records(Path(temp_dir), [
                {"session_id": "a", "payload": {"type": "function_call", "name": "shell_command", "call_id": "same", "arguments": json.dumps({"command": "tool --check"})}},
                {"session_id": "b", "payload": {"type": "function_call", "name": "shell_command", "call_id": "same", "arguments": json.dumps({"command": "tool --check"})}},
                {"session_id": "a", "payload": {"type": "function_call_output", "call_id": "same", "output": {"status": "failed", "detail": "secret body"}}},
                {"session_id": "b", "payload": {"type": "function_call_output", "call_id": "same", "output": {"success": False, "error": "other secret"}}},
                {"session_id": "a", "payload": {"type": "function_call", "name": "shell_command", "call_id": "later", "arguments": json.dumps({"command": "tool --check"})}},
                {"session_id": "a", "payload": {"type": "function_call_output", "call_id": "later", "output": {"status": "failed"}}},
            ])
            scan = PatternReader(str(path)).scan()
            facts = [fact for session in scan.sessions for fact in session.facts]
            self.assertEqual([fact.failure_fingerprint is not None for fact in facts], [True, True, True])
            self.assertFalse(any("secret" in repr(fact) for fact in facts))
            results = detect_observations(scan)
            self.assertEqual(next(item for item in results if item["id"] == "R-RETRY-01")["count"], 1)

    def test_retry_output_can_arrive_in_a_later_session_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            (directory / "01.jsonl").write_text(json.dumps({
                "session_id": "a",
                "payload": {"type": "function_call", "name": "shell_command", "call_id": "c", "arguments": json.dumps({"command": "tool --check"})},
            }) + "\n", encoding="utf-8")
            (directory / "02.jsonl").write_text(json.dumps({
                "session_id": "a",
                "payload": {"type": "function_call_output", "call_id": "c", "output": {"exit_code": 1}},
            }) + "\n", encoding="utf-8")
            (directory / "03.jsonl").write_text(json.dumps({
                "session_id": "a",
                "payload": {"type": "function_call", "name": "shell_command", "call_id": "d", "arguments": json.dumps({"command": "tool --check"})},
            }) + "\n", encoding="utf-8")
            (directory / "04.jsonl").write_text(json.dumps({
                "session_id": "a",
                "payload": {"type": "function_call_output", "call_id": "d", "output": {"exit_code": 1}},
            }) + "\n", encoding="utf-8")
            results = detect_observations(PatternReader(str(directory)).scan())
            self.assertEqual(next(item for item in results if item["id"] == "R-RETRY-01")["count"], 1)

    def test_unknown_repeated_failure_evidence_is_diagnostic_not_retry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self.write_records(Path(temp_dir), [
                {"session_id": "a", "payload": {"type": "function_call", "name": "shell_command", "call_id": "1", "arguments": json.dumps({"command": "tool --check"})}},
                {"session_id": "a", "payload": {"type": "function_call_output", "call_id": "1", "output": {"stdout": "no status"}}},
                {"session_id": "a", "payload": {"type": "function_call", "name": "shell_command", "call_id": "2", "arguments": json.dumps({"command": "tool --check"})}},
                {"session_id": "a", "payload": {"type": "function_call_output", "call_id": "2", "output": {"stdout": "still no status"}}},
            ])
            scan = PatternReader(str(path)).scan()
            self.assertEqual(detect_observations(scan), [])
            self.assertEqual(scan.diagnostics["retry_candidates_suppressed"], 1)

    def test_test_normalization_structured_intent_and_mutation_boundaries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self.write_records(Path(temp_dir), [
                {"session_id": "a", "payload": {"type": "function_call", "name": "shell_command", "call_id": "1", "arguments": json.dumps({"command": "python -m pytest tests/test_app.py"})}},
                {"session_id": "a", "payload": {"type": "function_call_output", "call_id": "1", "output": {"exit_code": 1}}},
                {"session_id": "a", "payload": {"type": "function_call", "name": "shell_command", "call_id": "2", "arguments": json.dumps({"command": "pytest tests/test_app.py"})}},
                {"session_id": "a", "payload": {"type": "function_call_output", "call_id": "2", "output": {"exit_code": 1}}},
                {"session_id": "a", "payload": {"type": "function_call", "name": "shell_command", "call_id": "3", "arguments": json.dumps({"command": "Get-Content app.py"})}},
                {"session_id": "a", "payload": {"type": "function_call_output", "call_id": "3", "output": {"exit_code": 0}}},
                {"session_id": "a", "payload": {"type": "patch_apply_end", "success": True}},
                {"session_id": "a", "payload": {"type": "function_call", "name": "shell_command", "call_id": "4", "arguments": json.dumps({"command": "pytest tests/test_app.py"})}},
                {"session_id": "a", "payload": {"type": "function_call_output", "call_id": "4", "output": {"exit_code": 1}}},
            ])
            scan = PatternReader(str(path)).scan()
            facts = scan.sessions[0].facts
            self.assertEqual([fact.kind for fact in facts], ["test", "test", "read", "mutation", "test"])
            self.assertEqual(facts[0].command, facts[1].command)
            results = detect_observations(scan)
            self.assertEqual(next(item for item in results if item["id"] == "R-TEST-01")["count"], 1)

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
