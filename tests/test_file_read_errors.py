import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from burnrate.parsers.claude_parser import ClaudeParser
from burnrate.parsers.codex_parser import CodexParser


class TestFileReadErrors(unittest.TestCase):
    parser_classes = (CodexParser, ClaudeParser)

    @staticmethod
    def _valid_record(parser_class, token_count):
        if parser_class is CodexParser:
            return {
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "model": "gpt-5.5",
                        "last_token_usage": {"input_tokens": token_count},
                    },
                },
            }
        return {
            "type": "assistant",
            "message": {
                "model": "claude-sonnet-4-5-20250929",
                "usage": {"input_tokens": token_count},
            },
        }

    @staticmethod
    def _write_record(path, record):
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    def test_os_error_in_one_file_does_not_stop_directory_scan(self):
        for parser_class in self.parser_classes:
            with self.subTest(parser=parser_class.__name__):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    first = root / "a-valid.jsonl"
                    failed = root / "b-unreadable.jsonl"
                    last = root / "c-valid.jsonl"
                    self._write_record(first, self._valid_record(parser_class, 10))
                    failed.touch()
                    self._write_record(last, self._valid_record(parser_class, 20))

                    original_open = open

                    def selective_open(file, *args, **kwargs):
                        if Path(file) == failed:
                            raise PermissionError("permission denied")
                        return original_open(file, *args, **kwargs)

                    parser = parser_class(log_path=str(root))
                    with patch("builtins.open", side_effect=selective_open):
                        with patch("sys.stdout", new=StringIO()) as output:
                            runs = parser.parse()

                    self.assertEqual(len(runs), 2)
                    self.assertEqual(parser.total_tokens, 30)
                    self.assertTrue(parser.scan_incomplete)
                    self.assertEqual(
                        parser.file_read_errors,
                        [
                            {
                                "filepath": str(failed),
                                "error": "PermissionError",
                                "message": "permission denied",
                            }
                        ],
                    )
                    diagnostic = output.getvalue()
                    self.assertEqual(diagnostic.count("Could not read"), 1)
                    self.assertIn(str(failed), diagnostic)
                    self.assertIn("permission denied", diagnostic)

    def test_single_undecodable_file_is_reported_and_state_resets(self):
        for parser_class in self.parser_classes:
            with self.subTest(parser=parser_class.__name__):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "undecodable.jsonl"
                    path.write_bytes(b"\xff\xfe\x00")
                    parser = parser_class(log_path=str(path))

                    with patch("sys.stdout", new=StringIO()) as output:
                        runs = parser.parse()

                    self.assertEqual(runs, [])
                    self.assertTrue(parser.scan_incomplete)
                    self.assertEqual(len(parser.file_read_errors), 1)
                    self.assertEqual(
                        parser.file_read_errors[0]["error"],
                        "UnicodeDecodeError",
                    )
                    self.assertIn(str(path), output.getvalue())
                    self.assertIn("invalid UTF-8", output.getvalue())

                    self._write_record(path, self._valid_record(parser_class, 10))
                    self.assertEqual(len(parser.parse()), 1)
                    self.assertFalse(parser.scan_incomplete)
                    self.assertEqual(parser.file_read_errors, [])

    def test_malformed_json_does_not_mark_a_readable_scan_incomplete(self):
        for parser_class in self.parser_classes:
            with self.subTest(parser=parser_class.__name__):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "malformed.jsonl"
                    path.write_text("not JSON\n", encoding="utf-8")
                    parser = parser_class(log_path=str(path))

                    self.assertEqual(parser.parse(), [])
                    self.assertEqual(parser.skip_counts["malformed_json"], 1)
                    self.assertFalse(parser.scan_incomplete)
                    self.assertEqual(parser.file_read_errors, [])


if __name__ == "__main__":
    unittest.main()
