import json
import shutil
import unittest
from unittest.mock import patch
from io import StringIO
from pathlib import Path

# Import the ClaudeParser and pricing dictionary for accurate calculations.
from burnrate.parsers.claude_parser import ClaudeParser, PRICING


class TestClaudeParser(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path("mock_claude_logs")
        # Create a temporary directory for mock log files before each test.
        self.test_dir.mkdir(exist_ok=True)

    def tearDown(self):
        # Clean up: remove all mock log files and the temporary directory after each test.
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_mock_log(self, filename: Path, data: list):
        """Helper method to write mock JSONL data to a specified file.

        Args:
            filename (Path): The path to the mock log file to create.
            data (list): A list of dictionaries, where each dictionary represents
                         a JSON log entry to be written as a line in the file.
        """
        filename.parent.mkdir(parents=True, exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f:
            for entry in data:
                f.write(json.dumps(entry) + "\n")

    def _claude_usage_record(
        self,
        input_tokens,
        request_id=None,
        timestamp=None,
        session_id="identity-session",
    ):
        record = {
            "type": "assistant",
            "sessionId": session_id,
            "message": {
                "model": "claude-sonnet-4-5-20250929",
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": 1,
                },
            },
        }
        if request_id is not None:
            record["requestId"] = request_id
        if timestamp is not None:
            record["timestamp"] = timestamp
        return record

    def test_parse_and_summary_basic(self):
        """Claude parses known-model usage and prints the expected totals."""
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
            self.assertIn("API-equivalent USD", output)
            self.assertIn("Estimates are not provider invoices.", output)
            self.assertIn("does not calculate Codex credit use.", output)

    def test_parse_and_summary_deduplication(self):
        """Claude keeps the latest cumulative usage for a repeated request ID."""
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
        self.assertEqual(final_run["session_id"], "claude-session-123")
        self.assertEqual(final_run["request_id"], "req_01_dedup")
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

    def test_same_request_id_in_different_sessions_is_retained(self):
        """Claude does not merge equal request IDs from distinct sessions."""
        test_filename = self.test_dir / "claude-sessions.jsonl"
        records = []
        for session_id, input_tokens in [("session-a", 100), ("session-b", 200)]:
            records.append({
                "type": "assistant",
                "sessionId": session_id,
                "requestId": "shared-request",
                "timestamp": "2026-05-25T20:00:00Z",
                "message": {
                    "model": "claude-sonnet-4-5-20250929",
                    "usage": {
                        "input_tokens": input_tokens,
                        "output_tokens": 20,
                    },
                },
            })
        self._create_mock_log(test_filename, records)

        parser = ClaudeParser(log_path=str(test_filename))
        runs = parser.parse()

        self.assertEqual(len(runs), 2)
        self.assertEqual(parser.total_tokens, 340)
        self.assertEqual(
            {(run["session_id"], run["request_id"]) for run in runs},
            {("session-a", "shared-request"), ("session-b", "shared-request")},
        )

    def test_records_without_request_ids_or_timestamps_are_preserved(self):
        """Claude gives every identity-deficient source record a unique key."""
        test_filename = self.test_dir / "identity-deficient.jsonl"
        repeated_timestamp = "2026-05-25T20:00:00Z"
        self._create_mock_log(test_filename, [
            self._claude_usage_record(10, timestamp=repeated_timestamp),
            self._claude_usage_record(20, timestamp=repeated_timestamp),
            self._claude_usage_record(30),
        ])

        parser = ClaudeParser(log_path=str(test_filename))
        runs = parser.parse()

        self.assertEqual(len(runs), 3)
        self.assertEqual(parser.total_tokens, 63)
        self.assertEqual({run["request_id"] for run in runs}, {None})
        self.assertEqual({run["source_line"] for run in runs}, {1, 2, 3})
        self.assertEqual(
            {run["filepath"] for run in runs},
            {str(test_filename.resolve())},
        )

    def test_cumulative_duplicate_uses_newest_parsed_timestamp(self):
        """Claude chooses cumulative usage by timestamp, not read order."""
        test_filename = self.test_dir / "out-of-order.jsonl"
        self._create_mock_log(test_filename, [
            self._claude_usage_record(
                200,
                request_id="cumulative-request",
                timestamp="2026-05-25T20:10:00Z",
            ),
            self._claude_usage_record(
                100,
                request_id="cumulative-request",
                timestamp="2026-05-25T20:00:00Z",
            ),
        ])

        run = ClaudeParser(log_path=str(test_filename)).parse()[0]

        self.assertEqual(run["input_tokens"], 200)
        self.assertEqual(run["source_line"], 1)

    def test_cumulative_timestamp_ties_use_filepath_and_line(self):
        """Claude breaks equal-timestamp ties by filepath and source line."""
        timestamp = "2026-05-25T20:00:00Z"
        first_file = self.test_dir / "a.jsonl"
        second_file = self.test_dir / "b.jsonl"
        self._create_mock_log(first_file, [
            self._claude_usage_record(100, "tied-request", timestamp),
            self._claude_usage_record(200, "tied-request", timestamp),
        ])

        first_run = ClaudeParser(log_path=str(first_file)).parse()[0]
        self.assertEqual(first_run["input_tokens"], 200)
        self.assertEqual(first_run["source_line"], 2)

        self._create_mock_log(second_file, [
            self._claude_usage_record(300, "tied-request", timestamp),
        ])
        final_run = ClaudeParser(log_path=str(self.test_dir)).parse()[0]
        self.assertEqual(final_run["input_tokens"], 300)
        self.assertEqual(final_run["filepath"], str(second_file.resolve()))

    def test_cache_read_and_creation_use_distinct_rates(self):
        """Claude applies distinct rates to cache reads and cache creation."""
        test_filename = self.test_dir / "mock_claude_pricing.jsonl"
        model = "claude-sonnet-4-5-20250929"
        self._create_mock_log(test_filename, [{
            "type": "assistant",
            "sessionId": "pricing-session",
            "requestId": "pricing-request",
            "timestamp": "2026-05-25T20:00:00Z",
            "message": {
                "model": model,
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cache_read_input_tokens": 40,
                    "cache_creation_input_tokens": 10,
                },
            },
        }])

        parser = ClaudeParser(log_path=str(test_filename))
        run = parser.parse()[0]
        pricing = PRICING[model]
        expected_cost = (
            100 * pricing["input"]
            + 20 * pricing["output"]
            + 40 * pricing["cache_read"]
            + 10 * pricing["cache_write"]
        )

        self.assertEqual(run["total_tokens"], 170)
        self.assertEqual(parser.total_cache_read, 40)
        self.assertEqual(parser.total_cache_creation, 10)
        self.assertAlmostEqual(run["cost"], expected_cost)
        self.assertAlmostEqual(parser.total_cost, expected_cost)

    def test_unknown_model_is_unpriced_and_reported(self):
        """Claude retains unknown-model usage and reports its cost as incomplete."""
        test_filename = self.test_dir / "mock_claude_unknown.jsonl"
        self._create_mock_log(test_filename, [{
            "type": "assistant",
            "requestId": "unknown-request",
            "timestamp": "2026-05-25T20:00:00Z",
            "message": {
                "model": "claude-unknown",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cache_read_input_tokens": 40,
                    "cache_creation_input_tokens": 10,
                },
            },
        }])

        parser = ClaudeParser(log_path=str(test_filename))
        run = parser.parse()[0]

        self.assertEqual(run["total_tokens"], 170)
        self.assertIsNone(run["cost"])
        self.assertEqual(parser.total_cost, 0.0)
        self.assertEqual(parser.unknown_models, {"claude-unknown"})

        with patch("sys.stdout", new=StringIO()) as fake_out:
            parser.summary()
        output = fake_out.getvalue()
        self.assertIn("UNPRICED", output)
        self.assertIn("claude-unknown", output)
        self.assertIn("incomplete", output)

    def test_malformed_and_non_object_records_are_skipped(self):
        """Claude skips damaged or non-object JSON and continues to valid usage."""
        test_filename = self.test_dir / "mock_claude_malformed.jsonl"
        valid_record = {
            "type": "assistant",
            "requestId": "valid-request",
            "timestamp": "2026-05-25T20:00:00Z",
            "message": {
                "model": "claude-sonnet-4-5-20250929",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                },
            },
        }
        malformed_lines = [
            "not valid JSON",
            "{}",
            "[]",
            "null",
            "42",
            json.dumps({"type": "assistant"}),
            json.dumps({"type": "assistant", "message": None}),
            json.dumps(valid_record),
        ]
        test_filename.write_text("\n".join(malformed_lines) + "\n", encoding="utf-8")

        parser = ClaudeParser(log_path=str(test_filename))
        runs = parser.parse()

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["total_tokens"], 120)
        self.assertEqual(parser.total_tokens, 120)

    def test_missing_path_clears_previous_results(self):
        """Claude clears previous results when a later parse path is missing."""
        test_filename = self.test_dir / "mock_claude_state.jsonl"
        self._create_mock_log(test_filename, [{
            "type": "assistant",
            "sessionId": "state-session",
            "requestId": "state-request",
            "timestamp": "2026-05-25T20:00:00Z",
            "message": {
                "model": "claude-sonnet-4-5-20250929",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                },
            },
        }])

        parser = ClaudeParser(log_path=str(test_filename))
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

    def test_repeated_parse_does_not_duplicate_results(self):
        """Claude produces identical state when the same file is parsed twice."""
        test_filename = self.test_dir / "mock_claude_repeated.jsonl"
        self._create_mock_log(test_filename, [{
            "type": "assistant",
            "sessionId": "repeat-session",
            "requestId": "repeat-request",
            "timestamp": "2026-05-25T20:00:00Z",
            "message": {
                "model": "claude-sonnet-4-5-20250929",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cache_read_input_tokens": 40,
                    "cache_creation_input_tokens": 10,
                },
            },
        }])

        parser = ClaudeParser(log_path=str(test_filename))
        first_runs = parser.parse().copy()
        first_state = (
            parser.total_tokens,
            parser.total_cost,
            parser.total_cache_read,
            parser.total_cache_creation,
            parser.models_used.copy(),
            parser.sessions.copy(),
            parser.stats_by_folder.copy(),
        )

        second_runs = parser.parse().copy()
        second_state = (
            parser.total_tokens,
            parser.total_cost,
            parser.total_cache_read,
            parser.total_cache_creation,
            parser.models_used.copy(),
            parser.sessions.copy(),
            parser.stats_by_folder.copy(),
        )

        self.assertEqual(second_runs, first_runs)
        self.assertEqual(second_state, first_state)

    def test_switching_paths_replaces_all_parser_state(self):
        """Claude replaces known-model state with unknown and then empty input."""
        known_file = self.test_dir / "known.jsonl"
        unknown_file = self.test_dir / "unknown.jsonl"
        empty_dir = self.test_dir / "empty"
        empty_dir.mkdir()
        self._create_mock_log(known_file, [{
            "type": "assistant",
            "sessionId": "known-session",
            "requestId": "known-request",
            "timestamp": "2026-05-25T20:00:00Z",
            "message": {
                "model": "claude-sonnet-4-5-20250929",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cache_read_input_tokens": 40,
                    "cache_creation_input_tokens": 10,
                },
            },
        }])
        self._create_mock_log(unknown_file, [{
            "type": "assistant",
            "sessionId": "unknown-session",
            "requestId": "unknown-request",
            "timestamp": "2026-05-26T20:00:00Z",
            "message": {
                "model": "claude-unknown",
                "usage": {"input_tokens": 10, "output_tokens": 2},
            },
        }])

        parser = ClaudeParser(log_path=str(known_file))
        parser.parse()
        self.assertGreater(parser.total_cost, 0)
        self.assertEqual(parser.total_cache_read, 40)
        self.assertEqual(parser.total_cache_creation, 10)

        parser.log_dir = unknown_file
        parser.parse()
        self.assertEqual(parser.total_tokens, 12)
        self.assertEqual(parser.total_cost, 0.0)
        self.assertEqual(parser.total_cache_read, 0)
        self.assertEqual(parser.total_cache_creation, 0)
        self.assertEqual(parser.models_used, {"claude-unknown"})
        self.assertEqual(parser.sessions, {"unknown-session"})
        self.assertEqual(parser.unknown_models, {"claude-unknown"})

        parser.log_dir = empty_dir
        self.assertEqual(parser.parse(), [])
        self.assertEqual(parser.total_tokens, 0)
        self.assertEqual(parser.total_cost, 0.0)
        self.assertEqual(parser.models_used, set())
        self.assertEqual(parser.sessions, set())
        self.assertEqual(parser.unknown_models, set())
        self.assertEqual(parser.stats_by_folder, {})
        empty_dir.rmdir()

if __name__ == "__main__":
    unittest.main()
