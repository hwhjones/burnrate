import json
import unittest

from burnrate.traces.normalize import normalize_events
from burnrate.traces.waste import CodexWasteAnalyzer


class TestAutomationFailureEpisodes(unittest.TestCase):
    def test_correlates_overlapping_checkpoint_failures_without_provider_ids(self):
        def event(line, timestamp, session):
            return {"event_type":"tool_output","timestamp":timestamp,"session_id":session,"command":"python scripts/tpm_radar_guard.py validate-import data/imports/gmail-2026-08-01.json","exit_status":1,"error_text":"Import contains Gmail IDs already checkpointed","source":{"filepath":"rollout.jsonl","line":line}}
        findings = CodexWasteAnalyzer().analyze(normalize_events([event(10,"2026-08-02T08:00:00Z","run-a"),event(20,"2026-08-02T08:01:00Z","run-b")]))["findings"]
        episode = next(item for item in findings if item["kind"] == "automation_failure_episode")
        self.assertEqual(episode["episode_type"], "duplicate_checkpoint_import")
        self.assertEqual(episode["confidence"], "high")
        self.assertEqual(episode["run_count"], 2)
        self.assertNotIn("Gmail IDs", json.dumps(episode))
        self.assertNotIn("19fb", json.dumps(episode))
        self.assertNotIn("message body", json.dumps(episode).lower())

    def test_classifies_schema_and_shell_failures_deterministically(self):
        events=[]
        for index,(command,error) in enumerate([("python -c query","sqlite3.OperationalError: no such column: o.id"),("python -c query","sqlite3.OperationalError: no such column: o.id"),("powershell -Command script","The string is missing the terminator"),("powershell -Command script","The string is missing the terminator")],1):
            events.append({"event_type":"tool_output","timestamp":f"2026-08-02T08:0{index}:00Z","session_id":f"run-{index}","command":command,"exit_status":1,"error_text":error,"source":{"filepath":"trace.jsonl","line":index}})
        findings=CodexWasteAnalyzer().analyze(normalize_events(events))["findings"]
        types={item["episode_type"] for item in findings if item["kind"] == "automation_failure_episode"}
        self.assertEqual(types,{"schema_query_mismatch","shell_quoting_failure"})


if __name__ == "__main__": unittest.main()