import json
import unittest
from pathlib import Path

from burnrate.traces import CodexTraceReader, CodexWasteAnalyzer, normalize_events


class TestTraceOutcomeEnvelope(unittest.TestCase):
    fixture = Path(__file__).parent / "fixtures" / "codex_trace" / "outcome_envelopes.jsonl"

    def test_extracts_only_status_and_error_presence_from_non_json_output(self):
        events = CodexTraceReader(str(self.fixture)).parse()
        outputs = [event for event in events if event["event_type"] == "tool_output"]
        self.assertEqual([event["exit_status"] for event in outputs], [0, 1, 1])
        self.assertNotIn("error_text", outputs[1])
        self.assertEqual(outputs[1]["error_evidence"], "stderr-present")
        rendered = json.dumps(events)
        self.assertNotIn("SENTINEL_SUCCESS_BODY_MUST_NOT_SURVIVE", rendered)
        self.assertNotIn("SENTINEL_FAILURE_BODY_MUST_NOT_SURVIVE", rendered)

    def test_recurring_failure_uses_status_and_error_evidence(self):
        events = normalize_events(CodexTraceReader(str(self.fixture)).parse())
        findings = CodexWasteAnalyzer().analyze(events)["findings"]
        failure = next(finding for finding in findings if finding["kind"] == "recurring_failure")
        self.assertEqual(failure["label"], "derived")
        self.assertEqual(failure["exit_status"], "failure:1")
        self.assertEqual(failure["error_evidence"], "stderr-present")
        self.assertEqual(failure["occurrences"], 2)


if __name__ == "__main__":
    unittest.main()
