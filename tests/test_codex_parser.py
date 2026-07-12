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
        """Test basic parsing and summary output with multiple token_count events."""
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


if __name__ == "__main__":
    unittest.main()
