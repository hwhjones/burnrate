import json
import unittest
from pathlib import Path

from burnrate.traces import CodexTraceReader


class TestCodexTraceReader(unittest.TestCase):
    fixture = Path(__file__).parent / "fixtures" / "codex_trace" / "representative.jsonl"

    def setUp(self):
        self.reader = CodexTraceReader(str(self.fixture))
        self.events = self.reader.parse()

    def test_retains_only_required_structured_evidence(self):
        self.assertEqual([event["event_type"] for event in self.events], [
            "tool_call", "tool_output", "token_count", "tool_call", "tool_output",
            "patch", "tool_call",
        ])
        call, output, tokens, failed_call, failed_output, patch, absent = self.events

        self.assertEqual(call["session_id"], "session-anon-01")
        self.assertEqual(call["agent_id"], "agent-child-01")
        self.assertEqual(call["parent_agent_id"], "agent-root-01")
        self.assertEqual(call["tool_name"], "shell_command")
        self.assertEqual(call["command"], "rg --files")
        self.assertEqual(call["path"], "C:/work/project")
        self.assertEqual(output["exit_status"], 0)
        self.assertEqual(output["tool_name"], "shell_command")
        self.assertEqual(tokens["token_snapshot"]["input_tokens"], 120)
        self.assertEqual(failed_call["command"], "git status")
        self.assertEqual(failed_output["exit_status"], 1)
        self.assertEqual(failed_output["error_text"], "repository unavailable")
        self.assertEqual(patch["mutation_status"], "succeeded")
        self.assertEqual(patch["path"], "C:/work/project/burnrate/traces/codex.py")
        self.assertNotIn("command", absent)

    def test_message_and_content_bodies_are_never_retained(self):
        rendered = json.dumps(self.events)
        for sentinel in (
            "SENTINEL_SYSTEM_BODY_MUST_NOT_SURVIVE",
            "SENTINEL_USER_BODY_MUST_NOT_SURVIVE",
            "SENTINEL_REASONING_BODY_MUST_NOT_SURVIVE",
            "SENTINEL_AGENT_BODY_MUST_NOT_SURVIVE",
            "SENTINEL_TOOL_OUTPUT_BODY_MUST_NOT_SURVIVE",
            "SENTINEL_PATCH_BODY_MUST_NOT_SURVIVE",
        ):
            self.assertNotIn(sentinel, rendered)

    def test_malformed_and_absent_fields_do_not_stop_the_reader(self):
        self.assertEqual(self.reader.skip_counts["malformed_json"], 1)
        self.assertEqual(self.reader.skip_counts["non_object_json"], 1)
        self.assertEqual(self.reader.skip_counts["invalid_record_shape"], 1)
        self.assertEqual(self.reader.file_read_errors, [])
        self.assertTrue(all("source" in event for event in self.events))


if __name__ == "__main__":
    unittest.main()
