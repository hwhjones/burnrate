import unittest

from burnrate.traces import CodexWasteAnalyzer, normalize_events


def trace_event(event_type, line, timestamp, **fields):
    return {
        "event_type": event_type,
        "timestamp": timestamp,
        "source": {"filepath": "trace.jsonl", "line": line},
        **fields,
    }


class TestMutationAwareRepetition(unittest.TestCase):
    def test_repeated_explicit_read_is_candidate_without_observed_mutation(self):
        events = normalize_events([
            trace_event("tool_call", 1, "2026-08-02T08:00:00Z", session_id="s", command="Get-Content -LiteralPath 'src/app.py'", path="C:/repo"),
            trace_event("tool_call", 2, "2026-08-02T08:01:00Z", session_id="s", command="Get-Content -LiteralPath 'src/app.py'", path="C:/repo"),
        ])
        findings = CodexWasteAnalyzer().analyze(events)["findings"]
        read = next(finding for finding in findings if finding["kind"] == "repeated_read_without_observed_mutation")
        self.assertEqual(read["read_path"], "src/app.py")
        self.assertIn("no observed successful mutation", read["confidence_rule"])

    def test_mutation_boundary_suppresses_read_candidate(self):
        events = normalize_events([
            trace_event("tool_call", 1, "2026-08-02T08:00:00Z", session_id="s", command="Get-Content -LiteralPath 'src/app.py'", path="C:/repo"),
            trace_event("patch", 2, "2026-08-02T08:00:30Z", session_id="s", mutation_status="succeeded", path="C:/repo/src/app.py"),
            trace_event("tool_call", 3, "2026-08-02T08:01:00Z", session_id="s", command="Get-Content -LiteralPath 'src/app.py'", path="C:/repo"),
        ])
        findings = CodexWasteAnalyzer().analyze(events)["findings"]
        self.assertFalse(any(finding["kind"] == "repeated_read_without_observed_mutation" for finding in findings))

    def test_repeated_failure_requires_status_and_no_observed_mutation(self):
        events = normalize_events([
            trace_event("tool_output", 1, "2026-08-02T08:00:00Z", session_id="s", command="pytest tests/unit.py", path="C:/repo", exit_status=1, error_evidence="stderr-present"),
            trace_event("tool_output", 2, "2026-08-02T08:01:00Z", session_id="s", command="pytest tests/unit.py", path="C:/repo", exit_status=1, error_evidence="stderr-present"),
        ])
        findings = CodexWasteAnalyzer().analyze(events)["findings"]
        repeated = next(finding for finding in findings if finding["kind"] == "repeated_failed_command_without_observed_mutation")
        self.assertEqual(repeated["exit_status"], "failure:1")
        self.assertEqual(repeated["label"], "derived")


if __name__ == "__main__":
    unittest.main()
