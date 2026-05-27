import json
from pathlib import Path
from .base import BaseParser

PRICING = {
    "claude-sonnet-4-5-20250929": {"input": 0.000001, "output": 0.000002},
    "claude-sonnet-4-20250929": {"input": 0.000001, "output": 0.000002},
    "claude-instant-1": {"input": 0.0000005, "output": 0.000001},
}
DEFAULT_PRICING = {"input": 0.000001, "output": 0.000002}

class ClaudeParser(BaseParser):
    """
    Parser for Anthropic Claude logs.
    """

    def __init__(self, log_path: str = '~/.claude/sessions/') -> None:
        self.log_dir = Path(log_path).expanduser()
        self.runs = []
        self.total_tokens = 0
        self.total_cost = 0.0
        self.models_used = set()
        self.sessions = set()

    def _extract_session_id(self, file_path: Path) -> str:
        stem = file_path.stem
        parts = stem.split("-")
        if len(parts) >= 5:
            return "-".join(parts[-5:])
        return stem

    def _calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        pricing = PRICING.get(model, DEFAULT_PRICING)
        return (input_tokens * pricing["input"]) + (output_tokens * pricing["output"])

    def _extract_model(self, data: dict) -> str:
        message = data.get("message") or {}
        return message.get("model") or data.get("model") or "claude"

    def _extract_usage(self, data: dict) -> dict:
        usage = data.get("usage")
        if isinstance(usage, dict):
            return usage
        message = data.get("message") or {}
        usage = message.get("usage")
        return usage if isinstance(usage, dict) else {}

    def parse(self) -> list[dict]:
        if not self.log_dir.exists():
            print(f"[CLAUDE] Error: Path {self.log_dir} not found.")
            return []

        if self.log_dir.is_file():
            files = [self.log_dir]
        elif self.log_dir.is_dir():
            files = sorted(self.log_dir.glob("**/*.jsonl"))
        else:
            print(f"[CLAUDE] Error: {self.log_dir} is not a file or directory.")
            return []

        self.runs = []
        self.total_tokens = 0
        self.total_cost = 0.0
        self.models_used.clear()
        self.sessions.clear()

        for file_path in files:
            if not file_path.is_file():
                continue

            session_id = self._extract_session_id(file_path)

            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    usage = self._extract_usage(data)
                    if not usage:
                        continue

                    input_tokens = usage.get("input_tokens", 0) or 0
                    output_tokens = usage.get("output_tokens", 0) or 0
                    total_tokens = usage.get("total_tokens") or (input_tokens + output_tokens)
                    if input_tokens == 0 and output_tokens == 0:
                        continue

                    model = self._extract_model(data)
                    cost = self._calculate_cost(input_tokens, output_tokens, model)
                    sid = data.get("sessionId") or data.get("session_id") or session_id
                    if sid:
                        self.sessions.add(sid)

                    message = data.get("message") or {}
                    entry = {
                        "timestamp": data.get("timestamp"),
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": total_tokens,
                        "model": model,
                        "cost": cost,
                        "session_id": sid,
                        "filepath": str(file_path),
                        "role": message.get("role"),
                        "message_type": message.get("type"),
                        "record_type": data.get("type"),
                    }
                    self.runs.append(entry)
                    self.total_tokens += total_tokens
                    self.total_cost += cost
                    self.models_used.add(model)

        return self.runs

    def summary(self) -> None:
        print(f"\n[CLAUDE] =========================")
        print(f"[CLAUDE] LOG ANALYSIS: {self.log_dir}")
        print(f"[CLAUDE] =========================")
        print(f"[CLAUDE] Session ID(s):  {', '.join(self.sessions) if self.sessions else 'Unknown'}")
        print(f"[CLAUDE] Models Used:    {', '.join(self.models_used) if self.models_used else 'None'}")
        print(f"[CLAUDE] Total LLM Runs: {len(self.runs)}")
        print(f"[CLAUDE] Total Tokens:   {self.total_tokens:,}")
        print(f"[CLAUDE] Total Cost:     ${self.total_cost:.6f}")
        print(f"[CLAUDE] =========================")
