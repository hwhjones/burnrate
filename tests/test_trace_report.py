import json
import unittest

from burnrate.traces.report import (
    finding_id,
    new_sidecar,
    record_finding_review,
    record_session,
    render_json,
    render_markdown,
    suggestion_text,
)


class TestTraceReport(unittest.TestCase):
    finding = {
        "kind": "repeated_read_without_observed_mutation",
        "label": "derived",
        "confidence": "medium",
        "confidence_rule": "no observed mutation",
        "command": "Get-Content README.md",
        "read_path": "README.md",
        "evidence": [{"filepath": "trace.jsonl", "line": 4}],
    }

    def test_sidecar_is_versioned_and_records_review_metadata(self):
        sidecar = new_sidecar()
        record_session(sidecar, "session-1", task_family="radar", outcome="completed", workflow_changed=False)
        key = record_finding_review(
            sidecar,
            self.finding,
            decision="no_change",
            category="expected-bootstrap",
            notes="No workflow change justified.",
        )
        self.assertEqual(sidecar["schema_version"], "codex-pilot-sidecar-v1")
        self.assertEqual(sidecar["sessions"]["session-1"]["task_family"], "radar")
        self.assertEqual(sidecar["findings"][key]["decision"], "no_change")
        self.assertEqual(key, finding_id(self.finding))

    def test_json_and_markdown_are_deterministic_and_body_free(self):
        sidecar = new_sidecar()
        record_finding_review(sidecar, self.finding, decision="change_workflow", notes="Cache this read.")
        analysis = {"findings": [self.finding]}
        first_json = render_json(analysis, sidecar)
        second_json = render_json(analysis, sidecar)
        self.assertEqual(first_json, second_json)
        self.assertIn("codex-pilot-report-v1", first_json)
        markdown = render_markdown(analysis, sidecar)
        self.assertIn("trace.jsonl:4", markdown)
        self.assertIn("change_workflow", markdown)
        self.assertNotIn("SENTINEL_MESSAGE_BODY", first_json + markdown)

    def test_suggestion_text_never_writes_targets_and_is_deterministic(self):
        sidecar = new_sidecar()
        record_finding_review(sidecar, self.finding, decision="change_workflow", category="read-cache", notes="Cache this read.")
        text = suggestion_text(sidecar)
        self.assertIn("Suggested workflow review items:", text)
        self.assertIn("Cache this read.", text)
        self.assertEqual(text, suggestion_text(sidecar))

    def test_rendered_json_is_valid(self):
        payload = json.loads(render_json({"findings": []}, new_sidecar()))
        self.assertEqual(payload["finding_count"], 0)


if __name__ == "__main__":
    unittest.main()
