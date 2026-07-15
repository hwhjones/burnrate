import unittest
from io import StringIO
from unittest.mock import patch

from burnrate.parsers.claude_parser import ClaudeParser
from burnrate.parsers.codex_parser import CodexParser


class TestUndatedProjections(unittest.TestCase):
    parser_classes = (CodexParser, ClaudeParser)

    def _run(self, timestamp, cost, input_tokens=100):
        return {
            "timestamp": timestamp,
            "model": "priced-model",
            "input_tokens": input_tokens,
            "output_tokens": 1,
            "reasoning_tokens": 0,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "cost": cost,
        }

    def _summary(self, parser_class, runs):
        parser = parser_class(log_path="unused")
        parser.runs = runs
        parser.total_tokens = sum(
            run["input_tokens"] + run["output_tokens"] for run in runs
        )
        parser.total_cost = sum(
            run["cost"] for run in runs if run["cost"] is not None
        )
        if any(run["cost"] is None for run in runs):
            parser.unknown_models = {"unpriced-model"}
        with patch("sys.stdout", new=StringIO()) as output:
            parser.summary()
        return output.getvalue()

    def test_all_dated_records_use_the_full_known_cost(self):
        runs = [
            self._run("2026-05-01T10:00:00Z", 2.0),
            self._run("2026-05-02T10:00:00Z", 4.0),
        ]
        for parser_class in self.parser_classes:
            with self.subTest(parser=parser_class.__name__):
                output = self._summary(parser_class, runs)
                self.assertIn("Observed period:                 2 day(s)", output)
                self.assertIn("Average daily API-equivalent USD: $3.00", output)
                self.assertIn("Projected 30-day API-equivalent USD: ~$90.00", output)
                self.assertNotIn("Undated records excluded", output)

    def test_mixed_records_keep_totals_but_project_only_dated_cost(self):
        runs = [
            self._run("2026-05-01T10:00:00Z", 2.0, 100),
            self._run(None, 10.0, 200),
        ]
        for parser_class in self.parser_classes:
            with self.subTest(parser=parser_class.__name__):
                output = self._summary(parser_class, runs)
                self.assertIn("UNDATED", output)
                self.assertIn("TOTALS", output)
                self.assertIn("300", output)
                self.assertIn("12.00", output)
                self.assertIn(
                    "Undated records excluded from projection: 1 ($10.00 known cost)",
                    output,
                )
                self.assertIn("Projected 30-day API-equivalent USD: ~$60.00", output)

    def test_all_undated_records_make_projection_unavailable(self):
        runs = [
            self._run(None, 2.0),
            self._run("", 4.0),
            self._run("invalid", None),
        ]
        for parser_class in self.parser_classes:
            with self.subTest(parser=parser_class.__name__):
                output = self._summary(parser_class, runs)
                self.assertIn(
                    "Undated records excluded from projection: 3 ($6.00 known cost)",
                    output,
                )
                self.assertIn(
                    "Projected 30-day API-equivalent USD: unavailable "
                    "(no valid dated records)",
                    output,
                )

    def test_invalid_timestamp_is_undated_without_hiding_valid_dates(self):
        runs = [
            self._run("2026-05-01T10:00:00Z", 2.0),
            self._run("not-a-timestamp", 10.0),
        ]
        for parser_class in self.parser_classes:
            with self.subTest(parser=parser_class.__name__):
                output = self._summary(parser_class, runs)
                self.assertIn("UNDATED", output)
                self.assertIn(
                    "Undated records excluded from projection: 1 ($10.00 known cost)",
                    output,
                )
                self.assertIn("Observed period:                 1 day(s)", output)
                self.assertIn("Projected 30-day API-equivalent USD: ~$60.00", output)

    def test_single_day_scan_uses_one_observed_day(self):
        runs = [
            self._run("2026-05-01T10:00:00Z", 2.0),
            self._run("2026-05-01T20:00:00+00:00", 4.0),
        ]
        for parser_class in self.parser_classes:
            with self.subTest(parser=parser_class.__name__):
                output = self._summary(parser_class, runs)
                self.assertIn("Observed period:                 1 day(s)", output)
                self.assertIn("Average daily API-equivalent USD: $6.00", output)
                self.assertIn("Projected 30-day API-equivalent USD: ~$180.00", output)
