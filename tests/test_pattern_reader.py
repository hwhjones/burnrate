import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from burnrate.analyser.patterns import PatternReader, SESSION_WORK_TOKEN_THRESHOLD, detect_observations


class PatternReaderTests(unittest.TestCase):
    def write_records(self, directory: Path, name: str, records: list[dict | str]) -> Path:
        path = directory / name
        lines = [record if isinstance(record, str) else json.dumps(record) for record in records]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_extracts_only_facts_needed_by_direct_rules(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self.write_records(Path(temp_dir), "session.jsonl", [
                {
                    "type": "event_msg",
                    "session_id": "session-a",
                    "timestamp": "2026-08-03T00:00:00Z",
                    "payload": {"type": "read_file", "path": "src\\app.py", "body": "secret"},
                    "message": "do not retain this",
                },
                {
                    "type": "event_msg",
                    "session_id": "session-a",
                    "timestamp": "2026-08-03T00:01:00Z",
                    "payload": {"type": "command_execution", "command": "pytest tests/test_app.py", "exit_code": 1, "error": "failed"},
                },
                {
                    "type": "event_msg",
                    "session_id": "session-a",
                    "timestamp": "2026-08-03T00:02:00Z",
                    "payload": {"type": "command_execution", "command": "apply_patch", "exit_code": 0, "success": True},
                },
            ])

            scan = PatternReader(str(path)).scan()

            self.assertEqual(scan.status, "complete")
            self.assertEqual(len(scan.sessions), 1)
            facts = scan.sessions[0].facts
            self.assertEqual([fact.kind for fact in facts], ["read", "test", "command"])
            self.assertEqual(facts[0].target, "src/app.py")
            self.assertEqual(facts[1].failure_fingerprint, "failed")
            self.assertTrue(facts[2].successful_mutation)
            self.assertFalse(any("secret" in repr(value) for value in scan.__dict__.values()))

    def test_final_token_usage_is_deduplicated_per_request_and_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self.write_records(Path(temp_dir), "sessions.jsonl", [
                {"type": "event_msg", "session_id": "a", "requestId": "r", "timestamp": "2026-08-03T00:00:00Z", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 10}}}},
                {"type": "event_msg", "session_id": "a", "requestId": "r", "timestamp": "2026-08-03T00:01:00Z", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 20}}}},
                {"type": "event_msg", "session_id": "b", "requestId": "r", "timestamp": "2026-08-03T00:00:00Z", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 30}}}},
            ])

            scan = PatternReader(str(path)).scan()

            by_session = {session.session_id: session for session in scan.sessions}
            self.assertEqual(by_session["a"].final_token_usage["r"]["usage"]["input_tokens"], 20)
            self.assertEqual(by_session["b"].final_token_usage["r"]["usage"]["input_tokens"], 30)

    def test_session_state_spans_files_with_monotonic_sequence_and_output_pairing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            self.write_records(directory, "01.jsonl", [
                {"session_id": "a", "payload": {"type": "function_call", "name": "shell_command", "call_id": "c", "arguments": json.dumps({"command": "tool --check"})}},
            ])
            self.write_records(directory, "02.jsonl", [
                {"session_id": "a", "payload": {"type": "function_call_output", "call_id": "c", "output": {"exit_code": 1}}},
                {"session_id": "a", "payload": {"type": "read_file", "path": "later.py"}},
            ])
            session = PatternReader(str(directory)).scan().sessions[0]
            self.assertEqual([fact.sequence for fact in session.facts], [0, 2])
            self.assertEqual(session.tool_output_events[0].sequence, 1)
            self.assertIsNotNone(session.facts[0].failure_fingerprint)

    def test_native_web_lifecycle_is_one_logical_occurrence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self.write_records(Path(temp_dir), "web.jsonl", [
                {"session_id": "a", "payload": {"type": "web_search_call", "call_id": "w1"}},
                {"session_id": "a", "payload": {"type": "web_search_end", "call_id": "w1", "output": "results"}},
            ])
            session = PatternReader(str(path)).scan().sessions[0]
            self.assertEqual(len(session.facts), 1)
            self.assertTrue(session.facts[0].web_call)
            results = detect_observations(PatternReader(str(path)).scan())
            self.assertEqual(next(item for item in results if item["id"] == "R-WEB-01")["count"], 1)

    def test_read_target_rejects_switches_and_variables(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self.write_records(Path(temp_dir), "reads.jsonl", [
                {"session_id": "a", "payload": {"type": "function_call", "name": "shell_command", "arguments": json.dumps({"command": "Get-Content -Raw"})}},
                {"session_id": "a", "payload": {"type": "function_call", "name": "shell_command", "arguments": json.dumps({"command": "Get-Content -Raw -LiteralPath app.py"})}},
                {"session_id": "a", "payload": {"type": "function_call", "name": "shell_command", "arguments": json.dumps({"command": "Get-Content $path"})}},
            ])
            facts = PatternReader(str(path)).scan().sessions[0].facts
            self.assertIsNone(facts[0].target)
            self.assertEqual(facts[1].target, "app.py")
            self.assertIsNone(facts[2].target)

    def test_token_snapshots_without_request_id_use_one_maximum_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self.write_records(Path(temp_dir), "tokens.jsonl", [
                {"session_id": "a", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 20}}}},
                {"session_id": "a", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": SESSION_WORK_TOKEN_THRESHOLD}}}},
                {"session_id": "a", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": SESSION_WORK_TOKEN_THRESHOLD}}}},
            ])
            session = PatternReader(str(path)).scan().sessions[0]
            self.assertEqual(session.token_accounting_source, "max_snapshot_without_request_id")
            self.assertEqual(len(session.anonymous_token_snapshots), 3)

    def test_malformed_records_do_not_stop_reading(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self.write_records(Path(temp_dir), "mixed.jsonl", [
                "not json",
                {"type": "event_msg", "session_id": "a", "payload": {"type": "read_file", "path": "a.py"}},
            ])

            scan = PatternReader(str(path)).scan()

            self.assertEqual(scan.status, "complete")
            self.assertEqual(scan.malformed_records, 1)
            self.assertEqual(len(scan.sessions[0].facts), 1)

    def test_unreadable_file_preserves_readable_sessions_and_marks_partial(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            good = self.write_records(directory, "good.jsonl", [
                {"type": "event_msg", "session_id": "good", "payload": {"type": "read_file", "path": "a.py"}},
            ])
            bad = self.write_records(directory, "bad.jsonl", [
                {"type": "event_msg", "session_id": "bad", "payload": {"type": "read_file", "path": "b.py"}},
            ])
            real_open = Path.open

            def open_file(path, *args, **kwargs):
                if path == bad:
                    raise PermissionError("permission denied")
                return real_open(path, *args, **kwargs)

            with patch.object(Path, "open", new=open_file):
                scan = PatternReader(str(directory)).scan()

            self.assertEqual(scan.status, "partial")
            self.assertEqual([session.session_id for session in scan.sessions], ["good"])
            self.assertEqual(len(scan.file_errors), 1)
    def test_invalid_and_empty_inputs_have_distinct_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            empty = Path(temp_dir) / "empty"
            empty.mkdir()
            self.assertEqual(PatternReader(str(empty)).scan().status, "empty")
            self.assertEqual(PatternReader(str(Path(temp_dir) / "missing.jsonl")).scan().status, "invalid")


if __name__ == "__main__":
    unittest.main()
