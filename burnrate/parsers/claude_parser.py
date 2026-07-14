import json
from datetime import date as calendar_date
from pathlib import Path
from collections import defaultdict
from .base import BaseParser
from ..pricing import CLAUDE_PRICING, calculate_cost

# Backward-compatible alias for existing imports.
PRICING = CLAUDE_PRICING
class ClaudeParser(BaseParser):
    """Parser implementation for Anthropic Claude JSONL session logs."""

    def __init__(self, log_path: str = '~/.claude/projects/') -> None:
        # Convert the provided path to an absolute home-expanded Path object.
        self.log_dir = Path(log_path).expanduser()
        self.runs = []
        self.total_tokens = 0
        self.total_cost = 0.0
        self.models_used = set()
        self.sessions = set()
        self.total_cache_read = 0
        self.total_cache_creation = 0
        # Reasoning tokens are not explicitly tracked for Claude logs in this parser.
        self.total_cache_read_cost = 0.0
        self.total_cache_creation_cost = 0.0
        self.stats_by_folder = {}
        self.unknown_models = set()

    def _extract_session_id(self, file_path: Path) -> str:
        """Construct a session identifier from a log file name."""
        stem = file_path.stem
        parts = stem.split("-")
        if len(parts) >= 5:
            # Use the trailing five components when the filename is long.
            return "-".join(parts[-5:])
        return stem

    def _extract_model(self, data: dict) -> str:
        """Extract the used model name from a log record."""
        message = data.get("message") or {}
        return message.get("model") or "claude"

    def _extract_usage(self, data: dict) -> dict:
        """Normalize the usage payload from different Claude record shapes."""
        usage = data.get("usage")
        return usage if isinstance(usage, dict) else (data.get("message", {}).get("usage") if isinstance(data.get("message"), dict) else {})

    def parse(self) -> list[dict]:
        """Parse Claude logs and produce a list of individual usage runs."""
        self.runs = []
        self.total_tokens = 0
        self.total_cost = 0.0
        self.models_used.clear()
        self.sessions.clear()
        self.total_cache_read = 0
        self.total_cache_creation = 0
        # self.total_reasoning_tokens = 0 # Reasoning tokens are not tracked for Claude
        self.total_cache_read_cost = 0.0
        self.total_cache_creation_cost = 0.0
        self.stats_by_folder.clear()
        self.unknown_models.clear()

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
        
        request_final_usages = {}

        for file_path in files:
            self._parse_file(file_path, request_final_usages)

        for rid, entry in request_final_usages.items():
            self.runs.append(entry)
            self.total_tokens += entry["total_tokens"]
            if entry["cost"] is not None:
                self.total_cost += entry["cost"]
            else:
                self.unknown_models.add(entry["model"])
            
            # Aggregate cache read tokens and their costs.
            if entry["cache_read_tokens"] > 0:
                self.total_cache_read += entry["cache_read_tokens"]
                self.total_cache_read_cost += entry["c_read_cost"]

            # Aggregate cache creation tokens and their costs.
            if entry["cache_creation_tokens"] > 0:
                self.total_cache_creation += entry["cache_creation_tokens"]
                self.total_cache_creation_cost += entry["c_create_cost"]

            self.models_used.add(entry["model"])
            
            # Update stats_by_folder using the filepath from the final entry
            folder = Path(entry["filepath"]).parent.name
            # Ensure folder is initialized, though it should be from the first loop
            if folder not in self.stats_by_folder:
                 self.stats_by_folder[folder] = {"runs": 0, "tokens": 0, "cost": 0.0}
            self.stats_by_folder[folder]["runs"] += 1
            self.stats_by_folder[folder]["tokens"] += entry["total_tokens"]
            self.stats_by_folder[folder]["cost"] += entry["cost"] or 0.0
        return self.runs

    def _parse_file(self, file_path: Path, request_final_usages: dict) -> None:
        """Extract usage from a single Claude log file and update the buffered collection.

        This method uses guard clauses to minimize nesting and improve readability.
        It processes each line, extracts relevant usage data, and stores it in
        `request_final_usages`, overwriting previous entries for the same request ID
        to capture the final cumulative usage.

        Args:
            file_path (Path): The path to the JSONL log file.
            request_final_usages (dict): A dictionary to store the latest usage entry
                                         for each unique request ID encountered across all files.
        """
        if not file_path.is_file():
            return

        session_id = self._extract_session_id(file_path)

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not isinstance(data, dict):
                    continue

                if data.get("type") != "assistant": # Only process assistant messages for usage
                    continue

                usage = self._extract_usage(data)
                if not usage:
                    continue

                input_tokens = usage.get("input_tokens", 0) or 0
                output_tokens = usage.get("output_tokens", 0) or 0
                cache_read = usage.get("cache_read_input_tokens", 0) or 0
                cache_create = usage.get("cache_creation_input_tokens", 0) or 0
                total_tokens = input_tokens + cache_create + cache_read + output_tokens

                if total_tokens == 0: # Skip if no tokens were used
                    continue

                request_id = data.get("requestId")
                if not request_id: # Must have a request_id for de-duplication
                    continue

                model = self._extract_model(data)
                costs = calculate_cost(
                    PRICING,
                    model,
                    input_tokens,
                    output_tokens,
                    cache_read_tokens=cache_read,
                    cache_write_tokens=cache_create,
                )
                
                sid = data.get("sessionId") or data.get("session_id") or session_id
                if sid:
                    self.sessions.add(sid) # Track unique session IDs
                request_final_usages[request_id] = {
                    "timestamp": data.get("timestamp"),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "cache_read_tokens": cache_read,
                    "cache_creation_tokens": cache_create,
                    "model": model,
                    "cost": costs["total"] if costs else None,
                    "c_read_cost": costs["cache_read"] if costs else 0.0,
                    "c_create_cost": costs["cache_write"] if costs else 0.0,
                    "filepath": str(file_path),
                }

    def summary(self) -> None:
        """Print a summary of the parsed Claude log analysis."""
        print(f"\n[CLAUDE] =========================")
        print(f"[CLAUDE] LOG ANALYSIS: {self.log_dir}")
        print(f"[CLAUDE] =========================")

        if not self.runs:
            print("[CLAUDE] No runs found to summarize.")
            print(f"[CLAUDE] =========================")
            return

        # Group runs by date and model
        # Using defaultdict to simplify aggregation
        grouped_stats = defaultdict(lambda: defaultdict(lambda: {
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "cache_creation": 0, # Add cache creation to grouped stats
            "cost": 0.0,
            "priced": True,
        }))

        for run in self.runs:
            date = run["timestamp"][:10] if run.get("timestamp") else "UNKNOWN_DATE"
            model = run.get("model", "UNKNOWN_MODEL")

            grouped_stats[date][model]["input"] += run.get("input_tokens", 0)
            grouped_stats[date][model]["output"] += run.get("output_tokens", 0)
            # Reasoning tokens are not tracked for Claude, so removed from aggregation
            # grouped_stats[date][model]["reasoning"] += run.get("reasoning_tokens", 0)
            grouped_stats[date][model]["cache_read"] += run.get("cache_read_tokens", 0)
            grouped_stats[date][model]["cache_creation"] += run.get("cache_creation_tokens", 0) # Aggregate cache creation
            if run.get("cost") is None:
                grouped_stats[date][model]["priced"] = False
            else:
                grouped_stats[date][model]["cost"] += run["cost"]

        # Print table header
        print(f"{'Date':<10} {'Model':<28} {'Input':>9} {'Output':>8} {'Cache Create':>12} {'Cache Read':>10} {'API-equivalent USD':>18}")
        print(f"{'-'*10} {'-'*28} {'-'*9} {'-'*8} {'-'*12} {'-'*10} {'-'*18}")

        # Print grouped data
        total_input_agg = 0
        total_output_agg = 0
        total_cache_read_agg = 0
        total_cache_creation_agg = 0 # Initialize aggregate for cache creation
        total_cost_agg = 0.0

        for date in sorted(grouped_stats.keys()):
            for model in sorted(grouped_stats[date].keys()):
                stats = grouped_stats[date][model]
                input_t = stats["input"]
                output_t = stats["output"]
                cache_r = stats["cache_read"]
                cache_c = stats["cache_creation"] # Get cache creation for current row
                cost_v = stats["cost"]
                cost_display = f"{cost_v:>18.2f}" if stats["priced"] else f"{'UNPRICED':>18}"

                total_input_agg += input_t
                total_output_agg += output_t
                total_cache_read_agg += cache_r
                total_cache_creation_agg += cache_c # Aggregate cache creation
                total_cost_agg += cost_v

                print(f"{date:<10} {model:<28} {input_t:>9,} {output_t:>8,} {cache_c:>12,} {cache_r:>10,} {cost_display}")

        # Print totals row
        print(f"{'-'*10} {'-'*28} {'-'*9} {'-'*8} {'-'*12} {'-'*10} {'-'*18}")
        print(f"{'TOTALS':<10} {'':<28} {total_input_agg:>9,} {total_output_agg:>8,} {total_cache_creation_agg:>12,} {total_cache_read_agg:>10,} {total_cost_agg:>18.2f}")
        print(f"[CLAUDE] =========================")

        # Additional metrics using the overall totals from parsing
        # Total cached includes both read and write/creation for Claude
        total_cached = self.total_cache_read + self.total_cache_creation
        cache_percentage = (total_cached / self.total_tokens * 100) if self.total_tokens > 0 else 0
        print(f"[CLAUDE] Cache tokens as % of all tokens: {cache_percentage:.2f}%")

        if self.unknown_models:
            models = ", ".join(sorted(self.unknown_models))
            print(f"[CLAUDE] Unpriced models:                  {models}")
            print("[CLAUDE] API-equivalent USD totals/projection: incomplete")
        else:
            try:
                dates = [
                    calendar_date.fromisoformat(run["timestamp"][:10])
                    for run in self.runs
                    if run.get("timestamp")
                ]
                observed_days = (max(dates) - min(dates)).days + 1
                average_daily_cost = self.total_cost / observed_days
                projected_30_day_cost = average_daily_cost * 30

                print(f"[CLAUDE] Observed period:                 {observed_days} day(s)")
                print(f"[CLAUDE] Average daily API-equivalent USD: ${average_daily_cost:.2f}")
                print(f"[CLAUDE] Projected 30-day API-equivalent USD: ~${projected_30_day_cost:.2f}")
            except (ValueError, TypeError):
                print("[CLAUDE] Projected 30-day API-equivalent USD: unavailable (invalid timestamps)")

        print("[CLAUDE] Estimates are not provider invoices.")
        print("[CLAUDE] BurnRate does not calculate Codex credit use.")
        print(f"[CLAUDE] =========================")
