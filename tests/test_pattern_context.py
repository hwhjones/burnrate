import json
import tempfile
import unittest
from pathlib import Path

from burnrate.analyser.patterns import PatternReader, detect_observations
from burnrate.analyser.pattern_catalog import (
    CARRY_INPUT_INCREASE_THRESHOLD,
    CONTEXT_GROWTH_MIN_TOKENS,
    CONTEXT_GROWTH_RUN_LENGTH,
    CONTEXT_UTILIZATION_THRESHOLD,
    LARGE_OUTPUT_CHAR_THRESHOLD,
    UNCACHED_INPUT_THRESHOLD,
    SESSION_WORK_TOKEN_THRESHOLD,
)


class PatternContextTests(unittest.TestCase):
    def write(self, records):
        temp = tempfile.TemporaryDirectory()
        path = Path(temp.name) / "session.jsonl"
        path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
        self.addCleanup(temp.cleanup)
        return path

    @staticmethod
    def token(input_tokens, *, cached=0, context=100_000, model="model-a", total=None, timestamp=None):
        usage = {"input_tokens": input_tokens, "cached_input_tokens": cached,
                 "cache_write_input_tokens": 0, "output_tokens": 10,
                 "reasoning_output_tokens": 2}
        if total is not None:
            usage["total_tokens"] = total
        record = {"session_id": "s", "payload": {"type": "token_count", "input_includes_cached": True, "info": {
            "model": model, "last_token_usage": usage,
        }, "model_context_window": context}}
        if timestamp:
            record["timestamp"] = timestamp
        return record

    def ids(self, records):
        scan = PatternReader(str(self.write(records))).scan()
        return {item["id"]: item for item in detect_observations(scan)}

    def test_context_utilization_below_and_at_threshold(self):
        below = self.ids([self.token(int(100_000 * CONTEXT_UTILIZATION_THRESHOLD) - 1)])
        at = self.ids([self.token(int(100_000 * CONTEXT_UTILIZATION_THRESHOLD))])
        self.assertNotIn("R-CTX-01", below)
        self.assertIn("R-CTX-01", at)

    def test_growth_below_and_at_run_length(self):
        below_records = [self.token(1_000)]
        for index in range(CONTEXT_GROWTH_RUN_LENGTH - 1):
            below_records.append(self.token(1_000 + (index + 1) * CONTEXT_GROWTH_MIN_TOKENS))
        at_records = below_records + [self.token(1_000 + CONTEXT_GROWTH_RUN_LENGTH * CONTEXT_GROWTH_MIN_TOKENS)]
        self.assertNotIn("R-CTX-02", self.ids(below_records))
        self.assertIn("R-CTX-02", self.ids(at_records))

    def test_cache_volume_is_non_negative_and_boundary_inclusive(self):
        below = self.ids([self.token(UNCACHED_INPUT_THRESHOLD, cached=1)])
        at = self.ids([self.token(UNCACHED_INPUT_THRESHOLD, cached=0)])
        negative = self.ids([self.token(1, cached=100)])
        self.assertNotIn("R-CACHE-01", below)
        self.assertIn("R-CACHE-01", at)
        self.assertNotIn("R-CACHE-01", negative)

    def test_incompatible_cache_semantics_suppress_cache_signal(self):
        record = self.token(UNCACHED_INPUT_THRESHOLD, cached=0)
        record["payload"]["input_includes_cached"] = False
        self.assertNotIn("R-CACHE-01", self.ids([record]))

    def test_missing_cache_semantics_and_inverted_counters_are_unavailable(self):
        missing = self.token(UNCACHED_INPUT_THRESHOLD, cached=0)
        missing["payload"].pop("input_includes_cached")
        inverted = self.token(UNCACHED_INPUT_THRESHOLD, cached=UNCACHED_INPUT_THRESHOLD + 1)
        self.assertNotIn("R-CACHE-01", self.ids([missing]))
        self.assertNotIn("R-CACHE-01", self.ids([inverted]))

    def test_carry_requires_ordered_output_and_followup_input(self):
        records = [
            self.token(1_000),
            {"session_id": "s", "payload": {"type": "function_call", "name": "shell_command", "call_id": "c", "arguments": json.dumps({"command": "tool"})}},
            {"session_id": "s", "payload": {"type": "function_call_output", "call_id": "c", "output": "x" * LARGE_OUTPUT_CHAR_THRESHOLD}},
            self.token(1_000 + CARRY_INPUT_INCREASE_THRESHOLD),
        ]
        self.assertIn("R-CARRY-01", self.ids(records))
        self.assertNotIn("R-CARRY-01", self.ids(records[:2] + [records[3]]))
        self.assertNotIn("R-CARRY-01", self.ids([records[0], records[1], records[2]]))

    def test_model_streams_do_not_combine_and_missing_snapshot_resets_growth(self):
        records = [
            self.token(1_000, model="model-a"),
            self.token(1_000 + CONTEXT_GROWTH_MIN_TOKENS, model="model-a"),
            {"session_id": "s", "payload": {"type": "token_count", "info": {"model": "model-a"}}},
            self.token(1_000 + 2 * CONTEXT_GROWTH_MIN_TOKENS, model="model-a"),
            self.token(90_000, context=200_000, model="model-b"),
        ]
        scan = PatternReader(str(self.write(records))).scan()
        session = scan.sessions[0]
        self.assertEqual([snapshot.model_id for snapshot in session.context_snapshots], ["model-a", "model-a", "model-a", "model-a", "model-b"])
        result = {item["id"]: item for item in detect_observations(scan)}
        self.assertNotIn("R-CTX-02", result)
        self.assertNotIn("R-CTX-01", result)

    def test_model_epochs_split_a_b_a_and_carry_turn_context_forward(self):
        records = [
            {"session_id": "s", "payload": {"type": "turn_context", "model": "model-a"}},
            self.token(1_000, model=None),
            self.token(1_000 + CONTEXT_GROWTH_MIN_TOKENS, model=None),
            {"session_id": "s", "payload": {"type": "turn_context", "model": "model-b"}},
            self.token(50, model=None),
            {"session_id": "s", "payload": {"type": "turn_context", "model": "model-a"}},
            self.token(3_048, model=None),
            self.token(4_072, model=None),
        ]
        scan = PatternReader(str(self.write(records))).scan()
        self.assertEqual(
            [(item.model_id, item.stream_epoch) for item in scan.sessions[0].context_snapshots],
            [("model-a", 0), ("model-a", 0), ("model-b", 1), ("model-a", 2), ("model-a", 2)],
        )
        result = {item["id"]: item for item in detect_observations(scan)}
        self.assertNotIn("R-CTX-02", result)

    def test_cumulative_component_snapshot_without_explicit_total_is_suppressed(self):
        records = [{
            "session_id": "s",
            "payload": {"type": "token_count", "info": {"total_token_usage": {
                "input_tokens": SESSION_WORK_TOKEN_THRESHOLD,
                "cached_input_tokens": 10_000,
                "output_tokens": 10_000,
                "reasoning_output_tokens": 2_000,
            }}},
        }]
        self.assertNotIn("R-TOKEN-01", self.ids(records))

    def test_context_result_exposes_measurement_contract_and_retains_no_bodies(self):
        records = [
            self.token(80_000),
            {"session_id": "s", "payload": {"type": "function_call_output", "output": "private-body"}},
        ]
        scan = PatternReader(str(self.write(records))).scan()
        result = next(item for item in detect_observations(scan) if item["id"] == "R-CTX-01")
        self.assertEqual(result["unit"], "ratio")
        self.assertEqual(result["threshold"], CONTEXT_UTILIZATION_THRESHOLD)
        self.assertTrue(result["telemetry_available"])
        self.assertEqual(result["examples"][0]["model_id"], "model-a")
        self.assertEqual(result["source_model_scope"], [{"model_id": "model-a", "stream_epoch": 0}])
        self.assertNotIn("private-body", repr(scan.__dict__))
        self.assertFalse(any(hasattr(snapshot, "output_body") for snapshot in scan.sessions[0].context_snapshots))

    def test_aggregate_model_scope_is_not_limited_to_display_examples(self):
        records = []
        for model in ("model-a", "model-b", "model-c", "model-d"):
            records.extend([
                {"session_id": "s", "payload": {"type": "turn_context", "model": model}},
                self.token(80_000, model=None),
            ])
        result = self.ids(records)["R-CTX-01"]
        self.assertEqual(len(result["examples"]), 3)
        self.assertEqual(result["count"], 4)
        self.assertEqual(
            result["source_model_scope"],
            [
                {"model_id": "model-a", "stream_epoch": 0},
                {"model_id": "model-b", "stream_epoch": 1},
                {"model_id": "model-c", "stream_epoch": 2},
                {"model_id": "model-d", "stream_epoch": 3},
            ],
        )


if __name__ == "__main__":
    unittest.main()
