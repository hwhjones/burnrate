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

    def test_bom_and_plain_utf8_preserve_first_record_and_diagnostics(self):
        for parser_class in self.parser_classes:
            for encoding in ("utf-8", "utf-8-sig"):
                for scan_mode in ("file", "directory"):
                    with self.subTest(
                        parser=parser_class.__name__,
                        encoding=encoding,
                        scan_mode=scan_mode,
                    ):
                        with tempfile.TemporaryDirectory() as directory:
                            root = Path(directory)
                            path = root / "usage.jsonl"
                            record = self._valid_record(parser_class, 10)
                            path.write_text(
                                f"{json.dumps(record)}\nnot JSON\n",
                                encoding=encoding,
                            )
                            log_path = path if scan_mode == "file" else root
                            parser = parser_class(log_path=str(log_path))

                            runs = parser.parse()

                            self.assertEqual(len(runs), 1)
                            self.assertEqual(parser.total_tokens, 10)
                            self.assertEqual(
                                parser.skip_counts["malformed_json"], 1
                            )
                            self.assertFalse(parser.scan_incomplete)
                            self.assertEqual(parser.file_read_errors, [])

    def test_missing_and_uninspectable_input_paths_are_distinct_from_scans(self):
        for parser_class in self.parser_classes:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for scenario in ("missing", "inaccessible"):
                    with self.subTest(parser=parser_class.__name__, scenario=scenario):
                        path = root / f"{scenario}.jsonl"
                        parser = parser_class(log_path=str(path))
                        stat_patch = (
                            patch.object(
                                type(path),
                                "stat",
                                side_effect=PermissionError("access denied"),
                            )
                            if scenario == "inaccessible"
                            else None
                        )

                        with patch("sys.stdout", new=StringIO()) as output:
                            if stat_patch is None:
                                runs = parser.parse()
                            else:
                                with stat_patch:
                                    runs = parser.parse()

                        self.assertEqual(runs, [])
                        self.assertTrue(parser.invalid_input_path)
                        self.assertFalse(parser.scan_incomplete)
                        self.assertEqual(output.getvalue().count("Could not inspect"), 1)
                        self.assertIn(str(path), output.getvalue())

    def test_empty_directory_is_a_complete_scan(self):
        for parser_class in self.parser_classes:
            with self.subTest(parser=parser_class.__name__):
                with tempfile.TemporaryDirectory() as directory:
                    parser = parser_class(log_path=directory)

                    self.assertEqual(parser.parse(), [])
                    self.assertFalse(parser.invalid_input_path)
                    self.assertFalse(parser.scan_incomplete)

    def test_discovery_error_preserves_files_and_resets_on_next_parse(self):
        for parser_class in self.parser_classes:
            with self.subTest(parser=parser_class.__name__):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    first_dir = root / "first"
                    restricted = root / "restricted"
                    second_dir = root / "second"
                    for path in (first_dir, restricted, second_dir):
                        path.mkdir()
                    first = first_dir / "usage.jsonl"
                    second = second_dir / "usage.jsonl"
                    self._write_record(first, self._valid_record(parser_class, 10))
                    self._write_record(second, self._valid_record(parser_class, 20))

                    def partial_walk(*args, onerror, **kwargs):
                        yield str(first_dir), [], [first.name]
                        error = PermissionError(13, "access denied", str(restricted))
                        onerror(error)
                        yield str(second_dir), [], [second.name]

                    parser = parser_class(log_path=str(root))
                    with patch(
                        "burnrate.parsers.base.os.walk",
                        side_effect=partial_walk,
                    ):
                        with patch("sys.stdout", new=StringIO()) as output:
                            runs = parser.parse()

                    self.assertEqual(len(runs), 2)
                    self.assertEqual(parser.total_tokens, 30)
                    self.assertFalse(parser.invalid_input_path)
                    self.assertTrue(parser.scan_incomplete)
                    self.assertEqual(parser.file_read_errors, [])
                    self.assertEqual(output.getvalue().count("Could not scan"), 1)
                    self.assertIn(str(restricted), output.getvalue())

                    self.assertEqual(len(parser.parse()), 2)
                    self.assertFalse(parser.invalid_input_path)
                    self.assertFalse(parser.scan_incomplete)


if __name__ == "__main__":
    unittest.main()
