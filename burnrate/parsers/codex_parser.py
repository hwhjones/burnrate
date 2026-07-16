import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict
from .base import BaseParser, parse_timestamp_date
from ..pricing import CODEX_PRICING, calculate_cost

# Backward-compatible alias for existing imports.
PRICING = CODEX_PRICING

class CodexParser(BaseParser):
    """Parser implementation for Codex-style JSONL session logs."""

    def __init__(self, log_path: str = "~/.codex/sessions/") -> None:
        self.log_dir = Path(log_path).expanduser()
        self.runs = []
        self.total_tokens = 0
        self.total_cost = 0.0
        self.models_used = set()
        self.sessions = set()
        self.total_cache_read = 0
        self.total_reasoning_tokens = 0
        self.total_cache_read_cost = 0.0
        self.stats_by_folder = {}
        self.unknown_models = set()
        self._reset_diagnostics()

    def _extract_session_id(self, file_path: Path) -> str:
        stem = file_path.stem
        parts = stem.split("-")
        if len(parts) >= 5:
            return "-".join(parts[-5:])
        return stem

    def parse(self) -> list[dict]:
        """Parse Codex logs into individual usage entries and aggregate totals."""
        self.runs = []
        self.total_tokens = 0
        self.total_cost = 0.0
        self.models_used.clear()
        self.sessions.clear()
        self.total_cache_read = 0
        self.total_reasoning_tokens = 0
        self.total_cache_read_cost = 0.0
        self.stats_by_folder.clear()
        self.unknown_models.clear()
        self._reset_diagnostics()

        if not self.log_dir.exists():
            print(f"[CODEX] Error: Directory {self.log_dir} not found.")
            return []

        if self.log_dir.is_file():
            files = [self.log_dir]
        elif self.log_dir.is_dir():
            files = sorted(self.log_dir.glob("**/*.jsonl"))
        else:
            print(f"[CODEX] Error: {self.log_dir} is not a file or directory.")
            return []

        # Scope known requests to sessions and preserve unknown requests by source.
        request_final_usages = {}

        for file_path in files:
            # Process each log file to populate the buffered collection.
            try:
                self._parse_file(file_path, request_final_usages)
            except (OSError, UnicodeError) as error:
                self._record_file_error("CODEX", file_path, error)

        for _, entry in request_final_usages.values():
            self.runs.append(entry)
            self.total_tokens += entry["total_tokens"]
            if entry["cost"] is not None:
                self.total_cost += entry["cost"]
            else:
                self.unknown_models.add(entry["model"])
            self.models_used.add(entry["model"])
            
            # Aggregate cache read tokens and their costs.
            if entry["cache_read_tokens"] > 0:
                self.total_cache_read += entry["cache_read_tokens"]
                self.total_cache_read_cost += entry["c_read_cost"]
            

            self.total_reasoning_tokens += entry["reasoning_tokens"]
            
            folder = Path(entry["filepath"]).parent.name
            if folder not in self.stats_by_folder:
                self.stats_by_folder[folder] = {"runs": 0, "tokens": 0, "cost": 0.0}
            
            self.stats_by_folder[folder]["runs"] += 1
            self.stats_by_folder[folder]["tokens"] += entry["total_tokens"]
            self.stats_by_folder[folder]["cost"] += entry["cost"] or 0.0

        return self.runs

    def _parse_file(self, file_path: Path, request_final_usages: dict) -> None:
        """Parse a Codex log file and update session-scoped final usages.

        Args:
            file_path (Path): The path to the JSONL log file.
            request_final_usages (dict): Selection order and final usage keyed
                by session/request or by source when the request ID is absent.
        """
        if not file_path.is_file():
            return

        current_model = "UNKNOWN_MODEL"
        session_id = self._extract_session_id(file_path)
        resolved_filepath = str(file_path.resolve())

        with open(file_path, 'r', encoding='utf-8') as f:
            for source_line, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    self._record_skip("malformed_json")
                    continue

                if not isinstance(data, dict):
                    self._record_skip("non_object_json")
                    continue

                msg_type = data.get("type")

                if msg_type == "turn_context":
                    payload = data.get("payload")
                    if not isinstance(payload, Mapping):
                        self._record_skip("invalid_record_shape")
                        continue
                    context_model = payload.get("model")
                    if context_model:
                        current_model = context_model
                    continue

                # Expected non-usage records are filtered without diagnostics.
                if msg_type == "response_item" or msg_type != "event_msg":
                    continue

                payload = data.get("payload")
                if not isinstance(payload, Mapping):
                    self._record_skip("invalid_record_shape")
                    continue
                if payload.get("type") != "token_count":
                    continue

                info = payload.get("info")
                if not isinstance(info, Mapping):
                    self._record_skip("invalid_record_shape", usage_like=True)
                    continue

                usage = info.get("last_token_usage")
                if usage is None or usage == {}:
                    self._record_skip("unusable_usage_record", usage_like=True)
                    continue
                if not isinstance(usage, Mapping):
                    self._record_skip("invalid_record_shape", usage_like=True)
                    continue

                token_fields = (
                    "input_tokens",
                    "cached_input_tokens",
                    "output_tokens",
                    "reasoning_output_tokens",
                )
                token_values = {}
                invalid_token_value = False
                for field in token_fields:
                    value = usage[field] if field in usage else 0
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, int)
                        or value < 0
                    ):
                        invalid_token_value = True
                        break
                    token_values[field] = value

                if invalid_token_value:
                    self._record_skip("unusable_usage_record", usage_like=True)
                    continue

                model = info.get("model") or current_model

                sid = data.get("session_id") or payload.get("session_id") or session_id
                if sid:
                    self.sessions.add(sid)

                gross_input = token_values["input_tokens"]
                cache_read = token_values["cached_input_tokens"]
                input_tokens = max(0, gross_input - cache_read) # Net input
                output_tokens = token_values["output_tokens"]
                reasoning = token_values["reasoning_output_tokens"]
                total_tokens = input_tokens + output_tokens + cache_read

                if total_tokens == 0:
                    self._record_skip("unusable_usage_record", usage_like=True)
                    continue

                request_id = data.get("requestId") or None
                costs = calculate_cost(
                    PRICING,
                    model,
                    input_tokens,
                    output_tokens,
                    cache_read_tokens=cache_read,
                )

                entry = {
                        "session_id": sid,
                        "request_id": request_id,
                        "timestamp": data.get("timestamp"),
                        "input_tokens": input_tokens,
                        "model": model,
                        "output_tokens": output_tokens,
                        "reasoning_tokens": reasoning,
                        "total_tokens": total_tokens,
                        "cache_read_tokens": cache_read,
                        "cost": costs["total"] if costs else None,
                        "c_read_cost": costs["cache_read"] if costs else 0.0,
                        "filepath": resolved_filepath,
                        "source_line": source_line,
                }
                parsed_timestamp = None
                timestamp = entry["timestamp"]
                if isinstance(timestamp, str):
                    try:
                        parsed_timestamp = datetime.fromisoformat(
                            timestamp.replace("Z", "+00:00")
                        )
                        if parsed_timestamp.tzinfo is None:
                            parsed_timestamp = parsed_timestamp.replace(
                                tzinfo=timezone.utc
                            )
                        else:
                            parsed_timestamp = parsed_timestamp.astimezone(
                                timezone.utc
                            )
                    except ValueError:
                        pass
                selection_order = (
                        parsed_timestamp is not None,
                        parsed_timestamp
                        or datetime.min.replace(tzinfo=timezone.utc),
                        resolved_filepath,
                        source_line,
                )
                identity = (
                        (sid, request_id)
                        if request_id is not None
                        else (sid, resolved_filepath, source_line)
                )
                existing = request_final_usages.get(identity)
                if existing is None or selection_order > existing[0]:
                    request_final_usages[identity] = (selection_order, entry)

    def summary(self):
        """Print a summary of the parsed Codex log analysis."""
        print(f"\n[CODEX] =========================")
        print(f"[CODEX] LOG ANALYSIS: {self.log_dir}")
        print(f"[CODEX] =========================")
        self._print_diagnostics("CODEX")

        if not self.runs:
            print("[CODEX] No runs found to summarize.")
            print(f"[CODEX] =========================")
            return

        # Group runs by date and model
        # Using defaultdict to simplify aggregation
        grouped_stats = defaultdict(lambda: defaultdict(lambda: {
            "input": 0,
            "output": 0,
            "reasoning": 0,
            "cache_read": 0,
            "cost": 0.0,
            "priced": True,
        }))

        dated_runs = []
        undated_runs = []
        for run in self.runs:
            parsed_date = parse_timestamp_date(run.get("timestamp"))
            if parsed_date is None:
                date = "UNDATED"
                undated_runs.append(run)
            else:
                date = parsed_date.isoformat()
                dated_runs.append((run, parsed_date))
            model = run.get("model", "UNKNOWN_MODEL")
            
            grouped_stats[date][model]["input"] += run.get("input_tokens", 0)
            grouped_stats[date][model]["output"] += run.get("output_tokens", 0)
            grouped_stats[date][model]["reasoning"] += run.get("reasoning_tokens", 0)
            grouped_stats[date][model]["cache_read"] += run.get("cache_read_tokens", 0)
            if run.get("cost") is None:
                grouped_stats[date][model]["priced"] = False
            else:
                grouped_stats[date][model]["cost"] += run["cost"]

        # Print table header
        print(f"{'Date':<10} {'Model':<28} {'Input':>9} {'Output':>8} {'Reasoning':>9} {'Cache Read':>10} {'API-equivalent USD':>18}")
        print(f"{'-'*10} {'-'*28} {'-'*9} {'-'*8} {'-'*9} {'-'*10} {'-'*18}")

        # Print grouped data
        total_input_agg = 0
        total_output_agg = 0
        total_reasoning_agg = 0
        total_cache_read_agg = 0
        total_cost_agg = 0.0

        for date in sorted(grouped_stats.keys()):
            for model in sorted(grouped_stats[date].keys()):
                stats = grouped_stats[date][model]
                input_t = stats["input"]
                output_t = stats["output"]
                reasoning_t = stats["reasoning"]
                cache_r = stats["cache_read"]
                cost_v = stats["cost"]
                cost_display = f"{cost_v:>18.2f}" if stats["priced"] else f"{'UNPRICED':>18}"

                total_input_agg += input_t
                total_output_agg += output_t
                total_reasoning_agg += reasoning_t
                total_cache_read_agg += cache_r
                total_cost_agg += cost_v

                print(f"{date:<10} {model:<28} {input_t:>9,} {output_t:>8,} {reasoning_t:>9,} {cache_r:>10,} {cost_display}")

        # Print totals row
        print(f"{'-'*10} {'-'*28} {'-'*9} {'-'*8} {'-'*9} {'-'*10} {'-'*18}")
        print(f"{'TOTALS':<10} {'':<28} {total_input_agg:>9,} {total_output_agg:>8,} {total_reasoning_agg:>9,} {total_cache_read_agg:>10,} {total_cost_agg:>18.2f}")
        print(f"[CODEX] =========================")

        # Additional metrics using the overall totals from parsing
        total_cached = self.total_cache_read
        cache_percentage = (total_cached / self.total_tokens * 100) if self.total_tokens > 0 else 0
        print(f"[CODEX] Cache tokens as % of all tokens: {cache_percentage:.2f}%")

        if undated_runs:
            undated_known_cost = sum(
                run["cost"] for run in undated_runs if run.get("cost") is not None
            )
            print(
                "[CODEX] Undated records excluded from projection: "
                f"{len(undated_runs)} (${undated_known_cost:.2f} known cost)"
            )

        if self.unknown_models:
            models = ", ".join(sorted(self.unknown_models))
            print(f"[CODEX] Unpriced models:                  {models}")
            print("[CODEX] API-equivalent USD totals/projection: incomplete")

        if not dated_runs:
            print("[CODEX] Projected 30-day API-equivalent USD: unavailable (no valid dated records)")
        elif not self.unknown_models:
            dates = [parsed_date for _, parsed_date in dated_runs]
            observed_days = (max(dates) - min(dates)).days + 1
            dated_known_cost = sum(
                run["cost"] for run, _ in dated_runs if run.get("cost") is not None
            )
            average_daily_cost = dated_known_cost / observed_days
            projected_30_day_cost = average_daily_cost * 30

            print(f"[CODEX] Observed period:                 {observed_days} day(s)")
            print(f"[CODEX] Average daily API-equivalent USD: ${average_daily_cost:.2f}")
            print(f"[CODEX] Projected 30-day API-equivalent USD: ~${projected_30_day_cost:.2f}")

        print("[CODEX] Estimates are not provider invoices.")
        print("[CODEX] BurnRate does not calculate Codex credit use.")
        print(f"[CODEX] =========================")
