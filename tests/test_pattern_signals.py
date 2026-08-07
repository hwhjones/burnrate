import json
import tempfile
import unittest
from pathlib import Path

from burnrate.analyser.patterns import (
    EXPLORATION_CALL_THRESHOLD,
    LARGE_OUTPUT_CHAR_THRESHOLD,
    SESSION_DURATION_SECONDS_THRESHOLD,
    SESSION_WORK_TOKEN_THRESHOLD,
    SUBAGENT_SPAWN_THRESHOLD,
    PatternReader,
    RULE_CATALOG,
    detect_observations,
)


class PatternSignalTests(unittest.TestCase):
    def write(self, records):
        temp = tempfile.TemporaryDirectory()
        path = Path(temp.name) / "session.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
        self.addCleanup(temp.cleanup)
        return path

    def ids(self, records):
        return {item["id"]: item for item in detect_observations(PatternReader(str(self.write(records))).scan())}

    def test_exploration_immediately_below_and_at_threshold(self):
        below = [{"session_id": "a", "payload": {"type": "read_file", "path": f"{i}.py", "turn_id": "t"}} for i in range(EXPLORATION_CALL_THRESHOLD - 1)]
        self.assertNotIn("R-EXP-01", self.ids(below))
        at = below + [{"session_id": "a", "payload": {"type": "read_file", "path": "at.py", "turn_id": "t"}}]
        self.assertEqual(self.ids(at)["R-EXP-01"]["count"], 1)

    def test_duration_and_tokens_are_session_local_and_boundary_inclusive(self):
        below = [
            {"session_id": "a", "timestamp": "2026-08-01T00:00:00Z", "payload": {"type": "read_file", "path": "a.py"}},
            {"session_id": "a", "timestamp": "2026-08-01T00:34:59Z", "payload": {"type": "read_file", "path": "b.py"}},
            {"session_id": "b", "timestamp": "2026-08-01T00:00:00Z", "payload": {"type": "read_file", "path": "c.py"}},
            {"session_id": "b", "timestamp": "2026-08-01T00:34:59Z", "payload": {"type": "read_file", "path": "d.py"}},
        ]
        below[0]["requestId"] = "r1"
        below[0]["payload"]["type"] = "token_count"
        below[0]["payload"]["info"] = {"last_token_usage": {"input_tokens": SESSION_WORK_TOKEN_THRESHOLD - 1}}
        self.assertNotIn("R-SESSION-01", self.ids(below))
        self.assertNotIn("R-TOKEN-01", self.ids(below))
        at = [
            {"session_id": "a", "timestamp": "2026-08-01T00:00:00Z", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": SESSION_WORK_TOKEN_THRESHOLD}}, "requestId": "r"}},
            {"session_id": "a", "timestamp": "2026-08-01T00:35:00Z", "payload": {"type": "read_file", "path": "a.py"}},
        ]
        result = self.ids(at)
        self.assertIn("R-SESSION-01", result)
        self.assertIn("R-TOKEN-01", result)

    def test_large_output_counts_direct_occurrences_at_threshold(self):
        def records(size):
            return [
                {"session_id": "a", "payload": {"type": "function_call", "name": "tool", "call_id": "c", "arguments": "{}"}},
                {"session_id": "a", "payload": {"type": "function_call_output", "call_id": "c", "output": "x" * size}},
            ]
        self.assertNotIn("R-OUT-01", self.ids(records(LARGE_OUTPUT_CHAR_THRESHOLD - 1)))
        self.assertEqual(self.ids(records(LARGE_OUTPUT_CHAR_THRESHOLD))["R-OUT-01"]["count"], 1)

    def test_subagent_requires_lineage_and_is_session_local(self):
        def records(count, lineage=True):
            return [{"session_id": "a", "payload": {"type": "subagent_spawn", "subagent_spawn": True, **({"lineage": {"parent": "a"}} if lineage else {})}} for _ in range(count)]
        self.assertNotIn("R-SUBAGENT-01", self.ids(records(SUBAGENT_SPAWN_THRESHOLD - 1)))
        self.assertEqual(self.ids(records(SUBAGENT_SPAWN_THRESHOLD))["R-SUBAGENT-01"]["affected_sessions"], 1)
        self.assertNotIn("R-SUBAGENT-01", self.ids(records(SUBAGENT_SPAWN_THRESHOLD, lineage=False)))

    def test_web_calls_are_direct_occurrences_and_missing_web_telemetry_suppresses_rule(self):
        records = [{"session_id": "a", "payload": {"type": "web_search", "web_call": True}} for _ in range(2)]
        self.assertEqual(self.ids(records)["R-WEB-01"]["count"], 2)
        self.assertNotIn("R-WEB-01", self.ids([{"session_id": "a", "payload": {"type": "command_execution", "command": "search"}}]))

    def test_missing_telemetry_suppresses_only_dependent_signals(self):
        records = [
            {"session_id": "a", "payload": {"type": "read_file", "path": "a.py"}},
            {"session_id": "a", "payload": {"type": "function_call", "name": "tool", "call_id": "c", "arguments": "{}"}},
            {"session_id": "a", "payload": {"type": "function_call_output", "call_id": "c"}},
            *[{"session_id": "a", "payload": {"type": "subagent_spawn", "subagent_spawn": True}} for _ in range(SUBAGENT_SPAWN_THRESHOLD)],
        ]
        result = self.ids(records)
        self.assertNotIn("R-EXP-01", result)
        self.assertNotIn("R-SESSION-01", result)
        self.assertNotIn("R-TOKEN-01", result)
        self.assertNotIn("R-OUT-01", result)
        self.assertNotIn("R-SUBAGENT-01", result)
        self.assertNotIn("R-WEB-01", result)


    def test_catalog_exposes_signal_contracts(self):
        thresholds = {
            "R-EXP-01": EXPLORATION_CALL_THRESHOLD,
            "R-SESSION-01": SESSION_DURATION_SECONDS_THRESHOLD,
            "R-TOKEN-01": SESSION_WORK_TOKEN_THRESHOLD,
            "R-OUT-01": LARGE_OUTPUT_CHAR_THRESHOLD,
            "R-SUBAGENT-01": SUBAGENT_SPAWN_THRESHOLD,
        }
        for rule_id, threshold in thresholds.items():
            self.assertEqual(RULE_CATALOG[rule_id]["threshold"], threshold)
            self.assertEqual(RULE_CATALOG[rule_id]["classification"], "frequency_signal")
        self.assertEqual(RULE_CATALOG["R-OUT-01"]["count_scope"], "direct_occurrences")
        self.assertEqual(RULE_CATALOG["R-WEB-01"]["count_scope"], "direct_occurrences")

    def test_missing_timestamp_suppresses_only_duration(self):
        records = [
            {"session_id": "a", "timestamp": "2026-08-01T00:00:00Z", "payload": {"type": "read_file", "path": "a.py"}},
            {"session_id": "a", "timestamp": "2026-08-01T00:35:00Z", "payload": {"type": "read_file", "path": "b.py"}},
            {"session_id": "a", "payload": {"type": "web_search", "web_call": True}},
        ]
        result = self.ids(records)
        self.assertNotIn("R-SESSION-01", result)
        self.assertIn("R-WEB-01", result)
if __name__ == "__main__":
    unittest.main()
