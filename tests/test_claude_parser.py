import os
import json
import sys

# Ensure we can import from the root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from parsers.claude_parser import ClaudeParser


def create_mock_log(filename):
    mock_data = [
        {
            "type": "assistant",
            "sessionId": "claude-session-123",
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
                    "cache_creation_input_tokens": 400,
                    "cache_read_input_tokens": 600,
                },
            },
        },
        {
            "type": "assistant",
            "sessionId": "claude-session-123",
            "timestamp": "2026-05-25T20:01:00Z",
            "message": {
                "model": "claude-sonnet-4-5-20250929",
                "id": "msg_02",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Here is the answer."}],
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 10,
                    "cache_creation_input_tokens": 420,
                    "cache_read_input_tokens": 620,
                },
            },
        },
    ]

    with open(filename, 'w', encoding='utf-8') as f:
        for entry in mock_data:
            f.write(json.dumps(entry) + "\n")


def run_test():
    test_dir = "mock_logs"
    os.makedirs(test_dir, exist_ok=True)
    test_filename = os.path.join(test_dir, "mock_claude.jsonl")
    create_mock_log(test_filename)
    parser = ClaudeParser(log_dir=test_dir)
    parser.parse()
    parser.summary()
    if os.path.exists(test_filename):
        os.remove(test_filename)
    if os.path.isdir(test_dir):
        os.rmdir(test_dir)


if __name__ == "__main__":
    run_test()
