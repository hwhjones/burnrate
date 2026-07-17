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
    def _codex_record(usage, model="gpt-5.5"):
        return {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "model": model,
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

    def _identity_contracts(self):
        return (
            (
                "codex",
                CodexParser,
                self._codex_record,
                "gpt-5.5",
                (
                    ("model", ("payload", "info", "model")),
                    ("primary_session", ("session_id",)),
                    ("secondary_session", ("payload", "session_id")),
                    ("request", ("requestId",)),
                ),
            ),
            (
                "claude",
                ClaudeParser,
                self._claude_record,
                "claude-sonnet-4-5-20250929",
                (
                    ("model", ("message", "model")),
                    ("primary_session", ("sessionId",)),
                    ("secondary_session", ("session_id",)),
                    ("request", ("requestId",)),
                ),
            ),
        )

    @staticmethod
    def _set_path(record, path, value):
        target = record
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    @staticmethod
    def _delete_path(record, path):
        target = record
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]

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
                "usage": {"input_tokens": 10},
            },
        ]

        parser, runs = self._parse_records(ClaudeParser, records)

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["total_tokens"], 10)
        self.assertEqual(runs[0]["model"], "UNKNOWN_MODEL")
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
        for invalid_value in invalid_values:
            usage = {
                "input_tokens": 10,
                "output_tokens": 1,
                "total_tokens": invalid_value,
            }
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
        self.assertEqual(parser.skip_counts["unusable_usage_record"], 30)
        self.assertEqual(parser.rejected_usage_records, 30)

    def test_codex_cross_field_token_invariants(self):
        records = []
        expected_totals = []
        models = ("gpt-5.5", "unknown-validation-model")
        valid_usages = (
            {
                "input_tokens": 10,
                "cached_input_tokens": 4,
                "output_tokens": 6,
                "reasoning_output_tokens": 2,
                "total_tokens": 16,
            },
            {
                "input_tokens": 10,
                "cached_input_tokens": 10,
                "output_tokens": 6,
                "reasoning_output_tokens": 6,
                "total_tokens": 16,
            },
            {"input_tokens": 10, "output_tokens": 6},
            {
                "input_tokens": 10,
                "cached_input_tokens": 0,
                "output_tokens": 6,
                "reasoning_output_tokens": 0,
                "total_tokens": 16,
            },
        )
        invalid_usages = (
            {
                "input_tokens": 10,
                "cached_input_tokens": 11,
                "output_tokens": 6,
            },
            {
                "input_tokens": 10,
                "output_tokens": 6,
                "reasoning_output_tokens": 7,
            },
            {"input_tokens": 10, "output_tokens": 6, "total_tokens": 15},
            {"input_tokens": 10, "output_tokens": 6, "total_tokens": 17},
        )

        for model in models:
            for usage in valid_usages:
                records.append(self._codex_record(usage, model=model))
                expected_totals.append(usage["input_tokens"] + usage["output_tokens"])
            for usage in invalid_usages:
                records.append(self._codex_record(usage, model=model))

        parser, runs = self._parse_records(CodexParser, records)

        self.assertEqual(len(runs), len(expected_totals))
        self.assertEqual([run["total_tokens"] for run in runs], expected_totals)
        self.assertEqual({run["model"] for run in runs}, set(models))
        self.assertEqual(parser.skip_counts["unusable_usage_record"], 8)
        self.assertEqual(parser.rejected_usage_records, 8)
        self.assertTrue(parser.totals_potentially_incomplete)

    def test_identity_metadata_types_are_strictly_validated(self):
        invalid_values = (True, 7, 7.5, [], {})
        for provider, parser_class, factory, known_model, fields in (
            self._identity_contracts()
        ):
            for field, path in fields:
                for value in invalid_values:
                    with self.subTest(provider=provider, field=field, value=value):
                        invalid = factory({"input_tokens": 10})
                        self._set_path(invalid, path, value)
                        parser, runs = self._parse_records(
                            parser_class,
                            [invalid, factory({"input_tokens": 10})],
                        )

                        self.assertEqual(len(runs), 1)
                        self.assertEqual(runs[0]["model"], known_model)
                        self.assertEqual(
                            parser.skip_counts["invalid_record_shape"], 1
                        )
                        self.assertEqual(parser.rejected_usage_records, 1)
                        self.assertTrue(parser.totals_potentially_incomplete)

    def test_codex_turn_context_model_types_are_strictly_validated(self):
        records = [
            {"type": "turn_context", "payload": {"model": value}}
            for value in (True, 7, 7.5, [], {})
        ]
        records.extend(
            [
                {"type": "turn_context", "payload": {"model": "gpt-5.5"}},
                {"type": "turn_context", "payload": {"model": None}},
                {"type": "turn_context", "payload": {"model": ""}},
            ]
        )
        usage_record = self._codex_record({"input_tokens": 10})
        del usage_record["payload"]["info"]["model"]
        records.append(usage_record)

        parser, runs = self._parse_records(CodexParser, records)

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["model"], "gpt-5.5")
        self.assertEqual(parser.skip_counts["invalid_record_shape"], 5)
        self.assertEqual(parser.rejected_usage_records, 0)
        self.assertFalse(parser.totals_potentially_incomplete)

    def test_missing_empty_and_valid_identity_metadata(self):
        valid_values = {
            "model": None,
            "primary_session": "primary-session",
            "secondary_session": "secondary-session",
            "request": "request-1",
        }
        for provider, parser_class, factory, known_model, fields in (
            self._identity_contracts()
        ):
            with self.subTest(provider=provider):
                absent = factory({"input_tokens": 10})
                self._delete_path(absent, fields[0][1])
                records = [absent]
                for missing_value in (None, ""):
                    record = factory({"input_tokens": 10})
                    for _, path in fields:
                        self._set_path(record, path, missing_value)
                    records.append(record)

                valid = factory({"input_tokens": 10})
                valid_values["model"] = known_model
                for (field, path) in fields:
                    self._set_path(valid, path, valid_values[field])
                records.append(valid)

                parser, runs = self._parse_records(parser_class, records)

                self.assertEqual(len(runs), 4)
                self.assertEqual(
                    [run["model"] for run in runs[:3]], ["UNKNOWN_MODEL"] * 3
                )
                self.assertTrue(all(run["cost"] is None for run in runs[:3]))
                self.assertTrue(
                    all(run["session_id"] == run["filepath"] for run in runs[:3])
                )
                self.assertTrue(all(run["request_id"] is None for run in runs[:3]))
                self.assertEqual(runs[3]["session_id"], "primary-session")
                self.assertEqual(runs[3]["request_id"], "request-1")
                self.assertEqual(runs[3]["model"], known_model)

    def _assert_path_unique_fallback(self, contract):
        provider, parser_class, factory, _, fields = contract
        with tempfile.TemporaryDirectory() as directory:
            provider_root = Path(directory) / provider
            paths = [
                provider_root / "first" / "session.jsonl",
                provider_root / "second" / "session.jsonl",
            ]
            request_path = dict(fields)["request"]
            for index, path in enumerate(paths, start=1):
                records = []
                for input_tokens in (index * 10, index * 20):
                    record = factory({"input_tokens": input_tokens})
                    self._set_path(record, request_path, "shared-request")
                    records.append(record)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    "\n".join(json.dumps(record) for record in records) + "\n",
                    encoding="utf-8",
                )

            runs = parser_class(log_path=str(provider_root)).parse()

            self.assertEqual(len(runs), 2)
            self.assertEqual({run["input_tokens"] for run in runs}, {20, 40})
            self.assertEqual(
                {run["session_id"] for run in runs},
                {str(path.resolve()) for path in paths},
            )
            self.assertTrue(all(run["session_id"] == run["filepath"] for run in runs))
            self.assertTrue(
                all(run["request_id"] == "shared-request" for run in runs)
            )

    def test_codex_fallback_session_contract(self):
        self._assert_path_unique_fallback(self._identity_contracts()[0])

    def test_claude_fallback_session_contract(self):
        self._assert_path_unique_fallback(self._identity_contracts()[1])

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
