import unittest

from burnrate.traces import CodexWasteAnalyzer, normalize_events, review_coverage, tune_thresholds, lower_signal_candidates, compute_baselines
from burnrate.traces.catalog import attach_catalog_metadata
from burnrate.traces.report import new_sidecar, record_finding_review, render_markdown, suggestion_text


def event(event_type, line, timestamp, **fields):
    return {
        "event_type": event_type,
        "timestamp": timestamp,
        "source": {"filepath": "catalog.jsonl", "line": line},
        **fields,
    }


class TestTraceCatalog(unittest.TestCase):
    def test_high_signal_candidates_have_stable_schema_and_metrics(self):
        events = normalize_events([
            event("tool_output", 1, "2026-08-02T08:00:00Z", session_id="s", command="pytest tests/test_app.py", path="C:/repo", exit_status=1),
            event("tool_output", 2, "2026-08-02T08:01:00Z", session_id="s", command="pytest tests/test_app.py", path="C:/repo", exit_status=1),
        ])
        findings = CodexWasteAnalyzer().analyze(events)["findings"]
        candidate = next(item for item in findings if item["kind"] == "test_churn_without_relevant_mutation")
        self.assertEqual(candidate["candidate_id"], "C1D-TEST-01")
        self.assertEqual(candidate["candidate_status"], "candidate")
        self.assertTrue(candidate["confirmation_required"])
        self.assertIn("repeated_operations", candidate["metrics"])
        self.assertFalse(candidate["baseline"]["evidence_available"])
        self.assertNotIn("waste", candidate["candidate_status"])

    def test_user_verdicts_are_recorded_without_changing_provider_evidence(self):
        finding = {"kind": "test_churn_without_relevant_mutation", "candidate_id": "C1D-TEST-01", "evidence": []}
        sidecar = new_sidecar()
        key = record_finding_review(sidecar, finding, decision="confirm", verdict="intentional", notes="Expected validation.")
        self.assertEqual(sidecar["findings"][key]["verdict"], "intentional")
        self.assertIn("C1D-TEST-01", render_markdown({"findings": [finding]}, sidecar))

    def test_lower_signal_catalog_is_explicitly_unavailable_and_baselined(self):
        events = normalize_events([
            event("tool_call", 1, "2026-08-01T08:00:00Z", session_id="s", command="rg --files", path="C:/repo"),
            event("token_count", 2, "2026-08-02T08:00:00Z", session_id="s", token_snapshot={"total_tokens": 100}),
        ])
        records = lower_signal_candidates(events, compute_baselines(events))
        self.assertEqual(len(records), 8)
        self.assertEqual({record["candidate_status"] for record in records}, {"candidate", "signal"})
        self.assertTrue(all(record["confirmation_required"] for record in records))
        self.assertTrue(all("evidence_limitation" in record for record in records))

    def test_investigation_candidates_use_exploration_rule_and_review_gate_is_explicit(self):
        finding = {"kind": "repeated_investigation_without_progress", "evidence": []}
        attach_catalog_metadata(finding, [])
        self.assertEqual(finding["candidate_id"], "C1D-EXP-01")
        sidecar = new_sidecar()
        record_finding_review(sidecar, finding, decision="change_workflow", verdict="intentional")
        self.assertEqual(suggestion_text(sidecar), "No workflow-change suggestions recorded.\n")
        record_finding_review(sidecar, finding, decision="change_workflow", verdict="avoidable")
        self.assertIn("Suggested workflow review items", suggestion_text(sidecar))
        coverage = review_coverage({"findings": [finding]}, sidecar)
        self.assertFalse(coverage["complete"])
        self.assertEqual(tune_thresholds(sidecar, minimum_verdicts=3)["status"], "insufficient_evidence")


if __name__ == "__main__":
    unittest.main()
