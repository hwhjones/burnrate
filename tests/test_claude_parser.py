import os
import json
import sys
import unittest
from unittest.mock import patch
from io import StringIO
from pathlib import Path

# Ensure we can import from the repository root for local parser tests.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Import the ClaudeParser for testing.
from parsers.claude_parser import ClaudeParser


class TestClaudeParser(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path("mock_claude_logs")
        # Create a temporary directory for mock log files before each test.
        self.test_dir.mkdir(exist_ok=True)

    def tearDown(self):
        # Clean up: remove all mock log files and the temporary directory after each test.
        for f in self.test_dir.glob("*.jsonl"):
            f.unlink()
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
        """Test basic parsing and summary output with a single request."""
        test_filename = self.test_dir / "mock_claude_basic.jsonl"
        mock_data = [
            {
                "type": "assistant",
                "sessionId": "claude-session-basic",
                "requestId": "req_basic_01",
                "timestamp": "2026-05-25T20:00:00Z",
                "message": {
                    "model": "claude-sonnet-4-5-20250929",
                    "id": "msg_01",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Hello!"}],
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                    },
                },
            },
        ]
        self._create_mock_log(test_filename, mock_data)

        parser = ClaudeParser(log_path=str(self.test_dir))
        runs = parser.parse()

        self.assertEqual(len(runs), 1)
        self.assertEqual(parser.total_tokens, 15) # 10 input + 5 output
        self.assertAlmostEqual(parser.total_cost, 0.000003 * 10 + 0.000015 * 5) # Using sonnet pricing
        self.assertEqual(parser.total_cache_read, 0)
        self.assertEqual(parser.total_cache_creation, 0)

        with patch('sys.stdout', new=StringIO()) as fake_out:
            parser.summary()
            output = fake_out.getvalue()
            self.assertIn("TOTALS", output)
            # Check for individual components in the table output
            self.assertIn("10", output) # Input tokens
            self.assertIn("5", output)  # Output tokens
            self.assertIn("0.00", output) # Total cost

    def test_parse_and_summary_deduplication(self):
        """Test that usage is de-duplicated by requestId, taking the last entry."""
        test_filename = self.test_dir / "mock_claude_dedup.jsonl"
        # Simulate multiple messages for the same requestId, with cumulative usage
        mock_data = [
            {
                "type": "assistant",
                "sessionId": "claude-session-123",
                "requestId": "req_01_dedup",
                "timestamp": "2026-05-25T20:00:00Z",
                "message": {
                    "model": "claude-sonnet-4-5-20250929",
                    "id": "msg_01",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Hello!"}],
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "cache_creation_input_tokens": 100,
                        "cache_read_input_tokens": 200,
                    },
                },
            },
            {
                "type": "assistant",
                "sessionId": "claude-session-123",
                "requestId": "req_01_dedup", # Same request ID
                "timestamp": "2026-05-25T20:01:00Z",
                "message": {
                    "model": "claude-sonnet-4-5-20250929",
                    "id": "msg_02",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Here is the answer."}],
                    "usage": {
                        "input_tokens": 15, # Cumulative input
                        "output_tokens": 8,  # Cumulative output
                        "cache_creation_input_tokens": 120, # Cumulative cache create
                        "cache_read_input_tokens": 250, # Cumulative cache read
                    },
                },
            },
        ]
        self._create_mock_log(test_filename, mock_data)

        parser = ClaudeParser(log_path=str(self.test_dir))
        runs = parser.parse()

        # Assert that only one run is captured due to requestId de-duplication.
        self.assertEqual(len(runs), 1) # Only one unique request_id
        final_run = runs[0]
        # Assert the values of the final (cumulative) run.
        self.assertEqual(final_run["input_tokens"], 15)
        self.assertEqual(final_run["output_tokens"], 8)
        self.assertEqual(final_run["cache_creation_tokens"], 120)
        self.assertEqual(final_run["cache_read_tokens"], 250)
        self.assertEqual(final_run["total_tokens"], 15 + 8 + 120 + 250)

        # Verify the parser's overall aggregate totals.
        self.assertEqual(parser.total_tokens, 15 + 8 + 120 + 250)
        self.assertEqual(parser.total_cache_read, 250)
        self.assertEqual(parser.total_cache_creation, 120)

        # Patch stdout to capture the summary output for string assertions.
        with patch('sys.stdout', new=StringIO()) as fake_out:
            parser.summary()
            output = fake_out.getvalue()
            self.assertIn("TOTALS", output)
            # Check for individual components in the table output
            self.assertIn("15", output)
            self.assertIn("8", output)
            self.assertIn("120", output)
            self.assertIn("250", output)
            self.assertIn("94.15%", output) # Cache percentage
            self.assertIn("250", output) # Cache Read
            self.assertIn("120", output) # Cache Create

if __name__ == "__main__":
    unittest.main()
