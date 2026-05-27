import os
import json
import sys

# Ensure we can import from the root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from parsers.codex_parser import CodexParser

def create_mock_log(filename):
    mock_data = [
        {
            "type": "event_msg",
            "session_id": "mock-session-uuid-123",
            "timestamp": "2026-05-25T20:00:00Z",
            "payload": {
                "type": "token_count",
                "info": {
                    "model": "gpt-4o-mini",
                    "last_token_usage": {"input_tokens": 2000, "output_tokens": 500}
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
                    "model": "gpt-4o-mini",
                    "last_token_usage": {"input_tokens": 5000, "output_tokens": 1200}
                }
            }
        }
    ]
    with open(filename, 'w', encoding='utf-8') as f:
        for entry in mock_data:
            f.write(json.dumps(entry) + "\n")

def run_test():
    test_dir = "mock_logs"
    os.makedirs(test_dir, exist_ok=True)
    test_filename = os.path.join(test_dir, "mock_test_rollout.jsonl")
    create_mock_log(test_filename)
    parser = CodexParser(log_dir=test_dir)
    parser.parse()
    parser.summary()
    if os.path.exists(test_filename):
        os.remove(test_filename)
    if os.path.isdir(test_dir):
        os.rmdir(test_dir)

if __name__ == "__main__":
    run_test()
