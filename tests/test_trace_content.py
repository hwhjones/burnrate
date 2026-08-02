import json
import unittest
from pathlib import Path

from burnrate.traces import CodexTraceReader, normalize_events
from burnrate.traces.normalize import normalize_message
from burnrate.traces.report import render_json, render_markdown


class TestTraceContentMode(unittest.TestCase):
    fixture = Path(__file__).parent / "fixtures" / "codex_trace" / "representative.jsonl"

    def test_default_path_remains_body_free(self):
        reader = CodexTraceReader(str(self.fixture))
        events = reader.parse()
        rendered = json.dumps(events)
        self.assertEqual(reader.content_manifest, [])
        self.assertNotIn("SENTINEL_USER_BODY_MUST_NOT_SURVIVE", rendered)
        self.assertNotIn("SENTINEL_AGENT_BODY_MUST_NOT_SURVIVE", rendered)

    def test_opt_in_content_is_in_order_and_provenanced(self):
        reader = CodexTraceReader(str(self.fixture))
        events = reader.parse(include_content=True)
        messages = [event for event in events if event["event_type"].endswith("_message")]
        self.assertEqual([event["event_type"] for event in messages], ["user_message", "agent_message"])
        self.assertEqual(messages[0]["message_text"], "SENTINEL_USER_BODY_MUST_NOT_SURVIVE")
        self.assertEqual(messages[1]["message_role"], "agent")
        self.assertEqual(
            [item["field"] for item in reader.content_manifest],
            ["payload.message", "payload.message"],
        )
        self.assertEqual([item["line"] for item in reader.content_manifest], [2, 4])
        self.assertEqual(messages[0]["source"]["line"], 2)

    def test_role_selection_is_explicit(self):
        reader = CodexTraceReader(str(self.fixture))
        events = reader.parse(include_content=True, content_roles={"user"})
        self.assertEqual(
            [event["event_type"] for event in events if event["event_type"].endswith("_message")],
            ["user_message"],
        )
        self.assertEqual(len(reader.content_manifest), 1)

    def test_message_features_mask_volatile_values_and_secrets(self):
        first = normalize_message(
            "Fix C:/Users/alice/app.py at 2026-08-02T08:00:00Z; token sk-testsecret123456"
        )
        second = normalize_message(
            "fix C:/Users/bob/app.py at 2026-08-03T09:00:00Z; token sk-othersecret654321"
        )
        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.assertNotIn("testsecret123456", first["terms"])
        self.assertNotIn("alice", first["terms"])
        self.assertGreater(first["token_count"], 0)

    def test_normalized_content_is_added_only_to_opt_in_events(self):
        reader = CodexTraceReader(str(self.fixture))
        events = normalize_events(reader.parse(include_content=True))
        message = next(event for event in events if event["event_type"] == "user_message")
        tool = next(event for event in events if event["event_type"] == "tool_call")
        self.assertIn("content_fingerprint", message["normalized"])
        self.assertIn("content_terms", message["normalized"])
        self.assertNotIn("content_fingerprint", tool["normalized"])

    def test_reports_manifest_without_message_body(self):
        reader = CodexTraceReader(str(self.fixture))
        reader.parse(include_content=True)
        analysis = {"findings": [], "inspection_manifest": reader.content_manifest}
        rendered_json = render_json(analysis)
        rendered_markdown = render_markdown(analysis)
        self.assertIn("inspection_manifest", rendered_json)
        self.assertIn("payload.message", rendered_markdown)
        self.assertNotIn("SENTINEL_USER_BODY_MUST_NOT_SURVIVE", rendered_json + rendered_markdown)
        self.assertNotIn("SENTINEL_AGENT_BODY_MUST_NOT_SURVIVE", rendered_json + rendered_markdown)


if __name__ == "__main__":
    unittest.main()