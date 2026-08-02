import unittest

from burnrate.traces import CodexWasteAnalyzer, normalize_events
from burnrate.traces.correlation import BOUNDARY_RULES, correlate_messages, segment_episodes
from burnrate.traces.report import new_sidecar, record_episode_review, record_finding_review


def event(event_type, line, timestamp, **fields):
    return {
        "event_type": event_type,
        "timestamp": timestamp,
        "source": {"filepath": "content-trace.jsonl", "line": line},
        **fields,
    }


class TestTraceCorrelation(unittest.TestCase):
    def test_boundaries_are_exposed_for_request_handoff_idle_context_and_terminal_events(self):
        events = normalize_events([
            event("user_message", 1, "2026-08-02T08:00:00Z", session_id="s", message_role="user", message_text="Investigate parser failures in app.py please"),
            event("tool_call", 2, "2026-08-02T08:01:00Z", session_id="s", agent_id="root", command="Get-Content -LiteralPath 'app.py'", path="C:/repo"),
            event("patch", 3, "2026-08-02T08:02:00Z", session_id="s", agent_id="root", mutation_status="succeeded", path="C:/repo/app.py"),
            event("tool_call", 4, "2026-08-02T08:03:00Z", session_id="s", agent_id="child", parent_agent_id="root", command="pytest tests/test_app.py", path="C:/repo"),
            event("tool_output", 5, "2026-08-02T08:04:00Z", session_id="s", agent_id="child", parent_agent_id="root", command="pytest tests/test_app.py", path="C:/repo", exit_status=0),
            event("tool_call", 6, "2026-08-02T08:25:00Z", session_id="s", agent_id="child", parent_agent_id="root", command="Get-Content -LiteralPath 'other.py'", path="C:/other"),
        ])
        episodes = segment_episodes(events)
        rules = {rule for episode in episodes for rule in episode["boundary_rules"]}
        self.assertTrue({"first_event", "agent_handoff", "idle_gap", "repository_or_workdir_change", "terminal_mutation", "terminal_test"} <= rules)
        self.assertEqual(set(BOUNDARY_RULES), {rule for rule in BOUNDARY_RULES})
        self.assertTrue(all(episode["boundary_evidence"] for episode in episodes))

    def test_content_match_needs_execution_and_absent_progress_before_candidate(self):
        events = normalize_events([
            event("user_message", 1, "2026-08-02T08:00:00Z", session_id="s", message_role="user", message_text="Investigate parser configuration errors in app.py"),
            event("tool_call", 2, "2026-08-02T08:01:00Z", session_id="s", command="Get-Content -LiteralPath 'app.py'", path="C:/repo"),
            event("user_message", 3, "2026-08-02T08:02:00Z", session_id="s", message_role="user", message_text="Investigate parser configuration errors in app.py"),
            event("tool_call", 4, "2026-08-02T08:03:00Z", session_id="s", command="Get-Content -LiteralPath 'app.py'", path="C:/repo"),
            event("tool_call", 5, "2026-08-02T08:04:00Z", session_id="s", command="Get-Content -LiteralPath 'app.py'", path="C:/repo"),
        ])
        analysis = CodexWasteAnalyzer().analyze(events)
        candidate = next(item for item in analysis["findings"] if item["kind"] == "repeated_investigation_without_progress")
        self.assertEqual(candidate["evidence_kind"], "combined")
        self.assertEqual(candidate["matching_rule"], "exact_normalized_fingerprint")
        self.assertTrue(candidate["shared_anchors"]["command"])
        self.assertEqual(candidate["progress_signal"], "no_progress_observed")

    def test_generic_and_quoted_messages_are_suppressed(self):
        events = normalize_events([
            event("user_message", 1, "2026-08-02T08:00:00Z", session_id="s", message_role="user", message_text="Thanks!"),
            event("tool_call", 2, "2026-08-02T08:01:00Z", session_id="s", command="Get-Content -LiteralPath 'app.py'", path="C:/repo"),
            event("user_message", 3, "2026-08-02T08:02:00Z", session_id="s", message_role="user", message_text="stdout: parser failures from command output"),
            event("tool_call", 4, "2026-08-02T08:03:00Z", session_id="s", command="Get-Content -LiteralPath 'app.py'", path="C:/repo"),
        ])
        result = correlate_messages(events)
        self.assertEqual(result["message_matches"], [])
        self.assertEqual(result["candidates"], [])

    def test_near_match_changed_context_and_missing_evidence_are_deterministic(self):
        near = normalize_events([
            event("user_message", 1, "2026-08-02T08:00:00Z", session_id="s", message_role="user", message_text="Please investigate parser configuration errors in app.py"),
            event("tool_call", 2, "2026-08-02T08:01:00Z", session_id="s", command="Get-Content -LiteralPath 'app.py'", path="C:/repo"),
            event("user_message", 3, "2026-08-02T08:02:00Z", session_id="s", message_role="user", message_text="Investigate parser configuration errors in app.py"),
            event("tool_call", 4, "2026-08-02T08:03:00Z", session_id="s", command="Get-Content -LiteralPath 'app.py'", path="C:/repo"),
        ])
        self.assertEqual(correlate_messages(near)["message_matches"][0]["matching_rule"], "term_containment")
        changed_context = normalize_events([
            event("user_message", 1, "2026-08-02T08:00:00Z", session_id="s", message_role="user", message_text="Investigate parser configuration errors in app.py"),
            event("tool_call", 2, "2026-08-02T08:01:00Z", session_id="s", command="Get-Content -LiteralPath 'app.py'", path="C:/repo"),
            event("user_message", 3, "2026-08-02T08:02:00Z", session_id="s", message_role="user", message_text="Plan the database migration for accounts schema"),
        ])
        self.assertEqual(correlate_messages(changed_context)["message_matches"], [])
        no_execution = normalize_events([
            event("user_message", 1, "2026-08-02T08:00:00Z", session_id="s", message_role="user", message_text="Investigate parser configuration errors in app.py"),
            event("user_message", 2, "2026-08-02T08:01:00Z", session_id="s", message_role="user", message_text="Investigate parser configuration errors in app.py"),
        ])
        result = correlate_messages(no_execution)
        self.assertTrue(result["message_matches"])
        self.assertFalse(result["message_matches"][0]["execution_evidence_present"])
        self.assertEqual(result["candidates"], [])

    def test_mutation_is_a_progress_exclusion_and_reviews_are_correctable(self):
        events = normalize_events([
            event("user_message", 1, "2026-08-02T08:00:00Z", session_id="s", message_role="user", message_text="Investigate parser configuration errors in app.py"),
            event("tool_call", 2, "2026-08-02T08:01:00Z", session_id="s", command="Get-Content -LiteralPath 'app.py'", path="C:/repo"),
            event("user_message", 3, "2026-08-02T08:02:00Z", session_id="s", message_role="user", message_text="Investigate parser configuration errors in app.py"),
            event("tool_call", 4, "2026-08-02T08:03:00Z", session_id="s", command="Get-Content -LiteralPath 'app.py'", path="C:/repo"),
            event("tool_call", 5, "2026-08-02T08:04:00Z", session_id="s", command="Get-Content -LiteralPath 'app.py'", path="C:/repo"),
            event("patch", 6, "2026-08-02T08:05:00Z", session_id="s", mutation_status="succeeded", path="C:/repo/app.py"),
        ])
        analysis = CodexWasteAnalyzer().analyze(events)
        self.assertFalse(any(item["kind"] == "repeated_investigation_without_progress" for item in analysis["findings"]))
        sidecar = new_sidecar()
        record_episode_review(sidecar, analysis["episodes"][0], decision="correct", correction="Merge with next episode")
        record_finding_review(sidecar, {"kind": "example", "evidence": []}, decision="reject")
        self.assertEqual(next(iter(sidecar["episodes"].values()))["decision"], "correct")
        self.assertEqual(next(iter(sidecar["findings"].values()))["decision"], "reject")


if __name__ == "__main__":
    unittest.main()
