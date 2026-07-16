import json
import tempfile
import unittest
from pathlib import Path

from burnrate.parsers.claude_parser import ClaudeParser
from burnrate.parsers.codex_parser import CodexParser


class TestParserValidation(unittest.TestCase):
    def _parse_records(self, parser_class, records):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "validation.jsonl"
            path.write_text(
                "\n".join(json.dumps(record) for record in records) + "\n",
                encoding="utf-8",
            )
            parser = parser_class(log_path=str(path))
            runs = parser.parse()
            return parser, runs

    @staticmethod
    def _codex_record(usage):
        return {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "model": "gpt-5.5",
                    "last_token_usage": usage,
                },
            },
        }

    @staticmethod
    def _claude_record(usage):
        return {
            "type": "assistant",
            "message": {
                "model": "claude-sonnet-4-5-20250929",
                "usage": usage,
            },
        }

    def test_codex_rejects_non_mapping_nested_payloads(self):
        records = [
            {"type": "turn_context", "payload": []},
            {"type": "turn_context", "payload": "invalid"},
            {"type": "event_msg", "payload": []},
            {"type": "event_msg", "payload": "invalid"},
            {
                "type": "event_msg",
                "payload": {"type": "token_count", "info": []},
            },
            {
                "type": "event_msg",
                "payload": {"type": "token_count", "info": "invalid"},
            },
            self._codex_record([]),
            self._codex_record("invalid"),
            self._codex_record({"input_tokens": 10}),
        ]

        parser, runs = self._parse_records(CodexParser, records)

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["total_tokens"], 10)
        self.assertEqual(parser.skip_counts["invalid_record_shape"], 8)
        self.assertEqual(parser.rejected_usage_records, 4)

    def test_claude_rejects_non_mapping_nested_payloads(self):
        records = [
            {"type": "assistant", "message": []},
            {"type": "assistant", "message": "invalid"},
            {"type": "assistant", "usage": []},
            {"type": "assistant", "usage": "invalid"},
            self._claude_record([]),
            self._claude_record("invalid"),
            {
                "type": "assistant",
                "message": [],
                "usage": {"input_tokens": 10},
            },
        ]

        parser, runs = self._parse_records(ClaudeParser, records)

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["total_tokens"], 10)
        self.assertEqual(runs[0]["model"], "claude")
        self.assertEqual(parser.skip_counts["invalid_record_shape"], 6)
        self.assertEqual(parser.rejected_usage_records, 6)

    def test_codex_token_values_are_strictly_validated(self):
        fields = (
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
        )
        invalid_values = (True, 1.5, "10", -1, None, [])
        records = []
        for field in fields:
            for invalid_value in invalid_values:
                usage = {"input_tokens": 10, "output_tokens": 1}
                usage[field] = invalid_value
                records.append(self._codex_record(usage))
        records.extend(
            [
                self._codex_record({"input_tokens": 10}),
                self._codex_record(
                    {
                        "input_tokens": 5,
                        "cached_input_tokens": 0,
                        "output_tokens": 0,
                        "reasoning_output_tokens": 0,
                    }
                ),
            ]
        )

        parser, runs = self._parse_records(CodexParser, records)

        self.assertEqual(len(runs), 2)
        self.assertEqual([run["total_tokens"] for run in runs], [10, 5])
        self.assertEqual(runs[1]["cache_read_tokens"], 0)
        self.assertEqual(runs[1]["reasoning_tokens"], 0)
        self.assertEqual(parser.skip_counts["unusable_usage_record"], 24)
        self.assertEqual(parser.rejected_usage_records, 24)

    def test_claude_token_values_are_strictly_validated(self):
        fields = (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        )
        invalid_values = (True, 1.5, "10", -1, None, [])
        records = []
        for field in fields:
            for invalid_value in invalid_values:
                usage = {"input_tokens": 10, "output_tokens": 1}
                usage[field] = invalid_value
                records.append(self._claude_record(usage))
        records.extend(
            [
                self._claude_record({"input_tokens": 10}),
                self._claude_record(
                    {
                        "input_tokens": 5,
                        "output_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 0,
                    }
                ),
            ]
        )

        parser, runs = self._parse_records(ClaudeParser, records)

        self.assertEqual(len(runs), 2)
        self.assertEqual([run["total_tokens"] for run in runs], [10, 5])
        self.assertEqual(runs[1]["cache_read_tokens"], 0)
        self.assertEqual(runs[1]["cache_creation_tokens"], 0)
        self.assertEqual(parser.skip_counts["unusable_usage_record"], 24)
        self.assertEqual(parser.rejected_usage_records, 24)


if __name__ == "__main__":
    unittest.main()
