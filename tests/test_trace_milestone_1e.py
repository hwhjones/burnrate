import unittest

from burnrate.traces import CodexWasteAnalyzer, normalize_events
from burnrate.traces.correlation import correlate_messages


def event(event_type, line, timestamp, **fields):
    return {
        "event_type": event_type,
        "timestamp": timestamp,
        "source": {"filepath": "milestone-1e.jsonl", "line": line},
        **fields,
    }


class TestMilestone1E(unittest.TestCase):
    def test_same_read_across_explicit_task_boundaries_is_not_missing_progress(self):
        events = normalize_events([
            event("tool_call", 1, "2026-08-02T08:00:00Z", session_id="s", command="Get-Content -LiteralPath 'app.py'", path="C:/repo"),
            event("user_message", 2, "2026-08-02T08:01:00Z", session_id="s", message_role="user", message_text="Now investigate the deployment configuration in deploy.yaml"),
            event("tool_call", 3, "2026-08-02T08:02:00Z", session_id="s", command="Get-Content -LiteralPath 'app.py'", path="C:/repo"),
        ])
        findings = CodexWasteAnalyzer().analyze(events)["candidate_findings"]
        self.assertFalse(any(item["candidate_id"] == "C1D-READ-01" for item in findings))

    def test_same_file_through_different_commands_is_one_read_occurrence(self):
        events = normalize_events([
            event("tool_call", 1, "2026-08-02T08:00:00Z", session_id="s", command="Get-Content -LiteralPath 'app.py'", path="C:/repo"),
            event("tool_call", 2, "2026-08-02T08:01:00Z", session_id="s", command="cat 'app.py'", path="C:/repo"),
        ])
        analysis = CodexWasteAnalyzer().analyze(events)
        finding = next(item for item in analysis["candidate_findings"] if item["candidate_id"] == "C1D-READ-01")
        self.assertEqual(finding["attempts"], 2)
        self.assertEqual(analysis["habit_summaries"][0]["occurrence_count"], 1)

    def test_metrics_use_token_delta_and_distinct_attempts(self):
        events = normalize_events([
            event("tool_output", 1, "2026-08-02T08:00:00Z", session_id="s", command="pytest tests/app.py", path="C:/repo", exit_status=1, token_snapshot={"total_tokens": 100}),
            event("tool_output", 2, "2026-08-02T08:01:00Z", session_id="s", command="pytest tests/app.py", path="C:/repo", exit_status=1, token_snapshot={"total_tokens": 240}),
        ])
        finding = next(item for item in CodexWasteAnalyzer().analyze(events)["candidate_findings"] if item["candidate_id"] == "C1D-TEST-01")
        self.assertEqual(finding["metrics"]["token_exposure"], 140)
        self.assertEqual(finding["metrics"]["attempts"], 2)
        self.assertEqual(finding["metrics"]["retries"], 1)
        self.assertEqual(finding["metrics"]["repeated_operations"], 2)

    def test_experimental_similarity_is_diagnostic_only(self):
        events = normalize_events([
            event("user_message", 1, "2026-08-02T08:00:00Z", session_id="s", message_role="user", message_text="Please investigate parser configuration errors in app.py"),
            event("tool_call", 2, "2026-08-02T08:01:00Z", session_id="s", command="Get-Content -LiteralPath 'app.py'", path="C:/repo"),
            event("user_message", 3, "2026-08-02T08:02:00Z", session_id="s", message_role="user", message_text="Investigate parser configuration errors in app.py"),
            event("tool_call", 4, "2026-08-02T08:03:00Z", session_id="s", command="Get-Content -LiteralPath 'app.py'", path="C:/repo"),
        ])
        result = correlate_messages(events)
        self.assertEqual(result["message_matches"][0]["matching_rule"], "term_containment")
        self.assertEqual(result["candidates"], [])


if __name__ == "__main__":
    unittest.main()

