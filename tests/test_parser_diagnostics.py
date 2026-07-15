import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from burnrate.parsers.claude_parser import ClaudeParser
from burnrate.parsers.codex_parser import CodexParser


class TestParserDiagnostics(unittest.TestCase):
    parser_classes = (CodexParser, ClaudeParser)

    def _records_for(self, parser_class):
        if parser_class is CodexParser:
            valid = {
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "model": "gpt-5.5",
                        "last_token_usage": {"input_tokens": 10},
                    },
                },
            }
            invalid_shape = {
                "type": "event_msg",
                "payload": {"type": "token_count", "info": []},
            }
            unusable_usage = {
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {"last_token_usage": {"input_tokens": "ten"}},
                },
            }
            irrelevant = {"type": "response_item", "payload": {}}
        else:
            valid = {
                "type": "assistant",
                "message": {
                    "model": "claude-sonnet-4-5-20250929",
                    "usage": {"input_tokens": 10},
                },
            }
            invalid_shape = {
                "type": "assistant",
                "message": {"usage": []},
            }
            unusable_usage = {
                "type": "assistant",
                "message": {"usage": {"input_tokens": "ten"}},
            }
            irrelevant = {"type": "user", "message": {}}
        return valid, invalid_shape, unusable_usage, irrelevant

    def _write_lines(self, path, lines):
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_each_category_mixed_files_and_incomplete_warning(self):
        for parser_class in self.parser_classes:
            with self.subTest(parser=parser_class.__name__):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    valid, invalid_shape, unusable_usage, irrelevant = (
                        self._records_for(parser_class)
                    )
                    self._write_lines(
                        root / "a-invalid.jsonl",
                        [
                            "not valid JSON",
                            "[]",
                            json.dumps(invalid_shape),
                            json.dumps(unusable_usage),
                        ],
                    )
                    self._write_lines(
                        root / "b-valid.jsonl",
                        [json.dumps(irrelevant), json.dumps(valid)],
                    )

                    parser = parser_class(log_path=str(root))
                    runs = parser.parse()

                    self.assertEqual(len(runs), 1)
                    self.assertEqual(
                        parser.skip_counts,
                        {
                            "malformed_json": 1,
                            "non_object_json": 1,
                            "invalid_record_shape": 1,
                            "unusable_usage_record": 1,
                        },
                    )
                    self.assertEqual(parser.rejected_usage_records, 2)
                    self.assertTrue(parser.totals_potentially_incomplete)

                    with patch("sys.stdout", new=StringIO()) as output:
                        parser.summary()
                    summary = output.getvalue()
                    self.assertIn("Skipped records:", summary)
                    self.assertIn("malformed JSON=1", summary)
                    self.assertIn("non-object JSON=1", summary)
                    self.assertIn("invalid shape=1", summary)
                    self.assertIn("unusable usage=1", summary)
                    self.assertIn(
                        "totals may be incomplete; 2 usage-like record(s) were rejected",
                        summary,
                    )

    def test_malformed_and_non_object_data_do_not_claim_lost_usage(self):
        for parser_class in self.parser_classes:
            with self.subTest(parser=parser_class.__name__):
                with tempfile.TemporaryDirectory() as directory:
                    _, _, _, irrelevant = self._records_for(parser_class)
                    path = Path(directory) / "non-usage.jsonl"
                    self._write_lines(
                        path,
                        ["not valid JSON", "null", json.dumps(irrelevant)],
                    )

                    parser = parser_class(log_path=str(path))
                    parser.parse()

                    self.assertEqual(parser.skip_counts["malformed_json"], 1)
                    self.assertEqual(parser.skip_counts["non_object_json"], 1)
                    self.assertEqual(parser.rejected_usage_records, 0)
                    self.assertFalse(parser.totals_potentially_incomplete)

                    with patch("sys.stdout", new=StringIO()) as output:
                        parser.summary()
                    self.assertIn("Skipped records:", output.getvalue())
                    self.assertNotIn("totals may be incomplete", output.getvalue())

    def test_repeated_parse_resets_diagnostics(self):
        for parser_class in self.parser_classes:
            with self.subTest(parser=parser_class.__name__):
                with tempfile.TemporaryDirectory() as directory:
                    valid, invalid_shape, _, _ = self._records_for(parser_class)
                    path = Path(directory) / "records.jsonl"
                    self._write_lines(
                        path,
                        ["not valid JSON", json.dumps(invalid_shape), json.dumps(valid)],
                    )
                    parser = parser_class(log_path=str(path))

                    parser.parse()
                    first_counts = parser.skip_counts.copy()
                    parser.parse()
                    self.assertEqual(parser.skip_counts, first_counts)
                    self.assertEqual(parser.rejected_usage_records, 1)

                    self._write_lines(path, [json.dumps(valid)])
                    parser.parse()
                    self.assertTrue(all(count == 0 for count in parser.skip_counts.values()))
                    self.assertEqual(parser.rejected_usage_records, 0)
                    self.assertFalse(parser.totals_potentially_incomplete)

                    with patch("sys.stdout", new=StringIO()) as output:
                        parser.summary()
                    self.assertNotIn("Skipped records:", output.getvalue())
