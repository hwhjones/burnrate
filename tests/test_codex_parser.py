import json
import unittest
from unittest.mock import patch
from io import StringIO
from pathlib import Path

# Import the CodexParser and its pricing dictionary for accurate test calculations.
from burnrate.parsers.codex_parser import CodexParser, PRICING


class TestCodexParser(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path("mock_codex_logs")
        # Create a temporary directory for mock log files before each test.
        self.test_dir.mkdir(exist_ok=True)

    def tearDown(self):
        # Clean up: remove all mock log files and the temporary directory after each test.
        for f in self.test_dir.glob("*.jsonl"):
            f.unlink()
        if self.test_dir.exists():
            self.test_dir.rmdir()

    def _create_mock_log(self, filename: Path, data: list):
        """Helper method to write mock JSONL data to a specified file.

        Args:
            filename (Path): The path to the mock log file to create.
            data (list): A list of dictionaries, where each dictionary represents
                         a JSON log entry to be written as a line in the file.
        """
        with open(filename, 'w', encoding='utf-8') as f:
            for entry in data:
                f.write(json.dumps(entry) + "\n")

    def test_parse_and_summary_basic(self):
        """Codex aggregates multiple token-count events and prints their totals."""
        test_filename = self.test_dir / "mock_codex_basic.jsonl"
        # Using larger numbers and gpt-5.5 so costs are visible in the .2f summary
        mock_data = [
            {
                "type": "event_msg",
                "session_id": "mock-session-uuid-123",
                "timestamp": "2026-05-25T20:00:00Z",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "model": "gpt-5.5",
                        "last_token_usage": {"input_tokens": 200000, "output_tokens": 50000}
                    }
                }
            },
            {
                "type": "event_msg",
                "session_id": "mock-session-uuid-123",
                "timestamp": "2026-05-25T20:02:00Z",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "model": "gpt-5.5",
                        "last_token_usage": {"input_tokens": 500000, "output_tokens": 120000}
                    }
                }
            }
        ]
        self._create_mock_log(test_filename, mock_data)

        parser = CodexParser(log_path=str(self.test_dir))
        runs = parser.parse()

        # Each token_count event is captured as a distinct run
        self.assertEqual(len(runs), 2) 
        
        expected_total_input = 200000 + 500000
        expected_total_output = 50000 + 120000
        
        model_pricing = PRICING["gpt-5.5"]
        cost_req1 = (200000 * model_pricing["input"]) + (50000 * model_pricing["output"])
        cost_req2 = (500000 * model_pricing["input"]) + (120000 * model_pricing["output"])
        expected_total_cost = cost_req1 + cost_req2

        self.assertEqual(parser.total_tokens, expected_total_input + expected_total_output)
        self.assertAlmostEqual(parser.total_cost, expected_total_cost)

        with patch('sys.stdout', new=StringIO()) as fake_out:
            parser.summary()
            output = fake_out.getvalue()
            self.assertIn("TOTALS", output)
            self.assertIn(f"{expected_total_input:,}", output)
            self.assertIn(f"{expected_total_output:,}", output)
            self.assertIn(f"{expected_total_cost:.2f}", output)

    def test_cached_input_and_reasoning_are_priced_once(self):
        """Codex prices cached input separately and does not double-charge reasoning."""
        test_filename = self.test_dir / "mock_codex_pricing.jsonl"
        self._create_mock_log(test_filename, [{
            "type": "event_msg",
            "session_id": "pricing-session",
            "timestamp": "2026-05-25T20:00:00Z",
            "payload": {
                "type": "token_count",
                "info": {
                    "model": "gpt-5.5",
                    "last_token_usage": {
                        "input_tokens": 1000,
                        "cached_input_tokens": 800,
                        "output_tokens": 200,
                        "reasoning_output_tokens": 50,
                    },
                },
            },
        }])

        parser = CodexParser(log_path=str(test_filename))
        run = parser.parse()[0]
        pricing = PRICING["gpt-5.5"]
        expected_cost = (
            200 * pricing["input"]
            + 800 * pricing["cache_read"]
            + 200 * pricing["output"]
        )

        self.assertEqual(run["input_tokens"], 200)
        self.assertEqual(run["cache_read_tokens"], 800)
        self.assertEqual(run["output_tokens"], 200)
        self.assertEqual(run["reasoning_tokens"], 50)
        self.assertEqual(run["total_tokens"], 1200)
        self.assertEqual(parser.total_reasoning_tokens, 50)
        self.assertAlmostEqual(run["cost"], expected_cost)
        self.assertAlmostEqual(parser.total_cost, expected_cost)

    def test_unknown_model_is_unpriced_and_reported(self):
        """Codex retains unknown-model usage and reports its cost as incomplete."""
        test_filename = self.test_dir / "mock_codex_unknown.jsonl"
        self._create_mock_log(test_filename, [{
            "type": "event_msg",
            "timestamp": "2026-05-25T20:00:00Z",
            "payload": {
                "type": "token_count",
                "info": {
                    "model": "gpt-unknown",
                    "last_token_usage": {
                        "input_tokens": 100,
                        "cached_input_tokens": 20,
                        "output_tokens": 30,
                    },
                },
            },
        }])

        parser = CodexParser(log_path=str(test_filename))
        run = parser.parse()[0]

        self.assertEqual(run["total_tokens"], 130)
        self.assertIsNone(run["cost"])
        self.assertEqual(parser.total_cost, 0.0)
        self.assertEqual(parser.unknown_models, {"gpt-unknown"})

        with patch("sys.stdout", new=StringIO()) as fake_out:
            parser.summary()
        output = fake_out.getvalue()
        self.assertIn("UNPRICED", output)
        self.assertIn("gpt-unknown", output)
        self.assertIn("incomplete", output)

    def test_missing_path_clears_previous_results(self):
        """Codex clears previous results when a later parse path is missing."""
        test_filename = self.test_dir / "mock_codex_state.jsonl"
        self._create_mock_log(test_filename, [{
            "type": "event_msg",
            "session_id": "state-session",
            "timestamp": "2026-05-25T20:00:00Z",
            "payload": {
                "type": "token_count",
                "info": {
                    "model": "gpt-5.5",
                    "last_token_usage": {
                        "input_tokens": 100,
                        "output_tokens": 20,
                    },
                },
            },
        }])

        parser = CodexParser(log_path=str(test_filename))
        self.assertEqual(len(parser.parse()), 1)
        self.assertGreater(parser.total_tokens, 0)

        parser.log_dir = self.test_dir / "missing.jsonl"
        with patch("sys.stdout", new=StringIO()):
            self.assertEqual(parser.parse(), [])

        self.assertEqual(parser.runs, [])
        self.assertEqual(parser.total_tokens, 0)
        self.assertEqual(parser.total_cost, 0.0)
        self.assertEqual(parser.models_used, set())
        self.assertEqual(parser.sessions, set())
        self.assertEqual(parser.unknown_models, set())


if __name__ == "__main__":
    unittest.main()
