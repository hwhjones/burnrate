import unittest
from pathlib import Path

from burnrate.traces import CodexTraceReader
from burnrate.traces.normalize import normalize_events
from burnrate.traces.waste import CodexWasteAnalyzer


def event(event_type, line, timestamp, **values):
    return {
        "event_type": event_type,
        "timestamp": timestamp,
        "source": {"filepath": "trace.jsonl", "line": line},
        **values,
    }


class TestCodexWasteAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = CodexWasteAnalyzer()

    def test_detects_repeated_commands_discovery_and_failures_across_sessions(self):
        events = normalize_events([
            event("tool_call", 1, "2026-08-02T08:00:00Z", session_id="one", command="rg --files", path="/home/a/repo"),
            event("tool_output", 2, "2026-08-02T08:00:01Z", session_id="one", command="rg --files", path="/home/a/repo", exit_status=1, error_text="repository unavailable 2026-08-02T08:00:01Z"),
            event("tool_call", 3, "2026-08-03T08:00:00Z", session_id="two", command=" rg   --files ", path="/home/b/repo/"),
            event("tool_output", 4, "2026-08-03T08:00:01Z", session_id="two", command="rg --files", path="/home/b/repo", exit_status=1, error_text="repository unavailable 2026-08-03T08:00:01Z"),
        ])
        findings = self.analyzer.analyze(events)["findings"]
        by_kind = {finding["kind"]: finding for finding in findings}

        self.assertEqual(by_kind["repeated_command_attempt"]["label"], "observed")
        self.assertEqual(by_kind["repeated_command_attempt"]["attempts"], 2)
        self.assertEqual(by_kind["repeated_repository_discovery"]["attempts"], 2)
        failure = by_kind["recurring_failure"]
        self.assertEqual(failure["label"], "derived")
        self.assertEqual(failure["exit_status"], "failure:1")
        self.assertEqual(len(failure["evidence"]), 2)

    def test_uses_last_snapshot_before_first_successful_mutation(self):
        events = normalize_events([
            event("token_count", 1, "2026-08-02T08:00:00Z", session_id="one", token_snapshot={"total_tokens": 100}),
            event("token_count", 2, "2026-08-02T08:05:00Z", session_id="one", token_snapshot={"total_tokens": 240}),
            event("patch", 3, "2026-08-02T08:06:00Z", session_id="one", mutation_status="succeeded", path="/home/a/repo/file.py"),
            event("token_count", 4, "2026-08-02T08:07:00Z", session_id="one", token_snapshot={"total_tokens": 300}),
            event("token_count", 5, "2026-08-02T08:00:00Z", session_id="two", token_snapshot={"total_tokens": 10}),
        ])
        findings = self.analyzer.analyze(events)["findings"]
        token_findings = {finding["session_id"]: finding for finding in findings if finding["kind"] == "tokens_before_first_successful_mutation"}

        self.assertEqual(token_findings["session-1"]["label"], "derived")
        self.assertEqual(token_findings["session-1"]["tokens_consumed"], 240)
        self.assertEqual(token_findings["session-2"]["label"], "unavailable")
        self.assertEqual(token_findings["session-2"]["confidence"], "none")

    def test_requires_multiple_independent_signals_for_subagent_duplication(self):
        events = normalize_events([
            event("tool_call", 1, "2026-08-02T08:00:00Z", session_id="one", agent_id="child-a", parent_agent_id="root", command="pytest tests/unit.py", path="/home/a/repo"),
            event("tool_call", 2, "2026-08-02T08:05:00Z", session_id="one", agent_id="child-b", parent_agent_id="root", command="pytest tests/unit.py", path="/home/a/repo"),
            event("tool_call", 3, "2026-08-02T10:00:00Z", session_id="one", agent_id="child-c", parent_agent_id="root", command="pytest tests/other.py", path="/home/a/elsewhere"),
        ])
        findings = self.analyzer.analyze(events)["findings"]
        duplicates = [finding for finding in findings if finding["kind"] == "probable_duplicated_subagent_work"]

        self.assertEqual(len(duplicates), 1)
        duplicate = duplicates[0]
        self.assertEqual(duplicate["label"], "heuristic")
        self.assertEqual(duplicate["confidence"], "high")
        self.assertIn("matching normalized command", duplicate["supporting_evidence"])
        self.assertIn("matching normalized path", duplicate["supporting_evidence"])
        self.assertIn("events within 30 minutes", duplicate["supporting_evidence"])

    def test_does_not_infer_duplicate_work_from_lineage_alone(self):
        events = normalize_events([
            event("tool_call", 1, "2026-08-02T08:00:00Z", session_id="one", agent_id="child-a", parent_agent_id="root", command="pytest a.py", path="/home/a/one"),
            event("tool_call", 2, "2026-08-02T10:00:00Z", session_id="one", agent_id="child-b", parent_agent_id="root", command="pytest b.py", path="/home/a/two"),
        ])
        findings = self.analyzer.analyze(events)["findings"]
        self.assertFalse(any(finding["kind"] == "probable_duplicated_subagent_work" for finding in findings))


    def test_detects_within_session_retries_without_claiming_cross_session_work(self):
        events = normalize_events([
            event("tool_call", 1, "2026-08-02T08:00:00Z", session_id="one", command="pytest tests/unit.py", path="/home/a/repo"),
            event("tool_call", 2, "2026-08-02T08:01:00Z", session_id="one", command="pytest tests/unit.py", path="/home/a/repo"),
        ])
        findings = self.analyzer.analyze(events)["findings"]
        repeated = next(finding for finding in findings if finding["kind"] == "repeated_command_attempt")

        self.assertEqual(repeated["sessions"], ["session-1"])
        self.assertEqual(repeated["confidence_rule"], "At least two tool-call events have the exact same normalized command and path.")

    def test_end_to_end_fixture_preserves_the_unavailable_evidence_boundary(self):
        fixture = Path(__file__).parent / "fixtures" / "codex_trace" / "representative.jsonl"
        events = CodexTraceReader(str(fixture)).parse()
        findings = self.analyzer.analyze(events)["findings"]
        token = next(
            finding for finding in findings
            if finding["kind"] == "tokens_before_first_successful_mutation"
        )

        self.assertEqual(token["label"], "derived")
        self.assertEqual(token["tokens_consumed"], 160)
        self.assertEqual(token["first_mutation_source"]["line"], 10)
        self.assertTrue(all(finding["label"] in {"observed", "derived", "heuristic", "unavailable"} for finding in findings))
if __name__ == "__main__":
    unittest.main()
