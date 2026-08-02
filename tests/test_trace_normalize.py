import unittest

from burnrate.traces.normalize import (
    classify_operation,
    normalize_command,
    normalize_error_text,
    normalize_events,
    normalize_exit_status,
    normalize_path,
)


class TestTraceNormalization(unittest.TestCase):
    def test_normalizes_volatile_values_to_an_exact_signature(self):
        event = {
            "event_type": "tool_output",
            "session_id": "d6c7fa12-61b4-4b00-bb20-d33d7a73f1c2",
            "agent_id": "agent-0f4e6a16c1734d2f",
            "timestamp": "2026-08-02T08:00:08.123Z",
            "tool_name": "shell_command",
            "command": "  pytest   tests/test_trace.py --run-id d6c7fa12-61b4-4b00-bb20-d33d7a73f1c2  ",
            "path": r"C:\\Users\\alice\\project\\runs\\d6c7fa12-61b4-4b00-bb20-d33d7a73f1c2",
            "exit_status": 1,
            "error_text": "Run d6c7fa12-61b4-4b00-bb20-d33d7a73f1c2 failed at 2026-08-02T08:00:08Z",
            "source": {"filepath": "raw.jsonl", "line": 8},
        }

        normalized = normalize_events([event])[0]

        self.assertEqual(normalized["operation"], "test")
        self.assertEqual(normalized["source"], event["source"])
        self.assertEqual(normalized["normalized"], {
            "session_id": "session-1",
            "agent_id": "agent-1",
            "timestamp": "<timestamp>",
            "command": "pytest tests/test_trace.py --run-id <uuid>",
            "path": "<home>/project/runs/<uuid>",
            "exit_status": "failure:1",
            "error_text": "run <uuid> failed at <timestamp>",
        })
        self.assertEqual(
            normalized["evidence_signature"]["fields"],
            {
                "event_type": "tool_output",
                "operation": "test",
                **normalized["normalized"],
            },
        )
        self.assertRegex(normalized["evidence_signature"]["value"], r"^sha256:[0-9a-f]{64}$")

    def test_equivalent_volatile_values_share_a_signature(self):
        first = {
            "event_type": "tool_call", "session_id": "a1b2c3d4-e5f6-4a7b-8c9d-e0f1a2b3c4d5",
            "timestamp": "2026-08-02T08:00:00Z", "command": "rg --files", "path": "/home/alice/project",
        }
        second = {
            "event_type": "tool_call", "session_id": "ffffeeee-dddd-4ccc-8bbb-aaaaaaaa1111",
            "timestamp": "2026-08-03T09:01:02Z", "command": " rg   --files ", "path": "/home/bob/project/",
        }
        first_normalized = normalize_events([first])[0]
        second_normalized = normalize_events([second])[0]
        self.assertEqual(first_normalized["operation"], "discovery")
        self.assertEqual(
            first_normalized["evidence_signature"]["value"],
            second_normalized["evidence_signature"]["value"],
        )

    def test_classification_rules_are_explicit(self):
        cases = {
            "rg --files": "discovery",
            "Get-Content README.md": "read",
            "Get-Content C:\\plugins\\skills\\gmail\\SKILL.md": "read",
            "python -m unittest": "test",
            "git status": "version-control",
            "gh auth login": "version-control",
            "aws login": "authentication",
            "python script.py": "unknown",
        }
        for command, expected in cases.items():
            with self.subTest(command=command):
                self.assertEqual(classify_operation({}, {"command": command}), expected)
        self.assertEqual(classify_operation({"event_type": "patch"}, {}), "mutation")

    def test_small_helpers_reject_malformed_values(self):
        self.assertIsNone(normalize_command(3))
        self.assertIsNone(normalize_path({}))
        self.assertIsNone(normalize_exit_status(True))
        self.assertIsNone(normalize_error_text([]))


if __name__ == "__main__":
    unittest.main()
