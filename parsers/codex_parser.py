import json
import re
from pathlib import Path
from .base import BaseParser

# Pricing constants
PRICING = {
    "gpt-4o-mini": {"input": 0.00000015, "output": 0.0000006},
}

class CodexParser(BaseParser):
    def __init__(self, log_path: str = "~/.codex/sessions/") -> None:
        raw_path = Path(log_path).expanduser()
        if raw_path.suffix == ".jsonl":
            self.log_dir = raw_path.parent
        else:
            self.log_dir = raw_path
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

    def _calculate_cost(self, input_tokens, output_tokens, model):
        p = PRICING.get(model, PRICING["gpt-4o-mini"])
        return (input_tokens * p["input"]) + (output_tokens * p["output"])

    def parse(self) -> list[dict]:
        if not self.log_dir.exists():
            print(f"[CODEX] Error: Directory {self.log_dir} not found.")
            return []

        if not self.log_dir.is_dir():
            print(f"[CODEX] Error: {self.log_dir} is not a directory.")
            return []

        self.runs = []
        self.total_tokens = 0
        self.total_cost = 0.0
        self.models_used.clear()
        self.sessions.clear()

        for file_path in sorted(self.log_dir.glob("**/*.jsonl")):
            if not file_path.is_file():
                continue

            prev_input = 0
            prev_output = 0
            session_id = self._extract_session_id(file_path)

            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        sid = data.get("session_id") or data.get("payload", {}).get("session_id") or session_id
                        if sid:
                            self.sessions.add(sid)

                        if data.get("type") == "event_msg":
                            payload = data.get("payload") or {}
                            if payload.get("type") == "token_count":
                                info = payload.get("info") or {}
                                model = info.get("model", "gpt-4o-mini")
                                usage = info.get("last_token_usage") or {}
                                if usage:
                                    input_cum = usage.get("input_tokens", 0)
                                    output_cum = usage.get("output_tokens", 0)
                                    delta_in = max(0, input_cum - prev_input)
                                    delta_out = max(0, output_cum - prev_output)

                                    if delta_in > 0 or delta_out > 0:
                                        cost = self._calculate_cost(delta_in, delta_out, model)
                                        entry = {
                                            "timestamp": data.get("timestamp"),
                                            "input_tokens": delta_in,
                                            "model": model,
                                            "output_tokens": delta_out,
                                            "total_tokens": delta_in + delta_out,
                                            "cost": cost,
                                            "session_id": session_id,
                                            "filepath": str(file_path),
                                        }
                                        self.runs.append(entry)
                                        self.total_tokens += entry["total_tokens"]
                                        self.total_cost += cost
                                        self.models_used.add(model)
                                        prev_input = input_cum
                                        prev_output = output_cum
                    except json.JSONDecodeError:
                        continue
        return self.runs

    def summary(self):
        print(f"\n[CODEX] =========================")
        print(f"[CODEX] LOG ANALYSIS: {self.log_dir}")
        print(f"[CODEX] =========================")
        print(f"[CODEX] Session ID(s):  {', '.join(self.sessions) if self.sessions else 'Unknown'}")
        print(f"[CODEX] Models Used:    {', '.join(self.models_used) if self.models_used else 'None'}")
        print(f"[CODEX] Total LLM Runs: {len(self.runs)}")
        print(f"[CODEX] Total Tokens:   {self.total_tokens:,}")
        print(f"[CODEX] Total Cost:     ${self.total_cost:.6f}")
        print(f"[CODEX] =========================")