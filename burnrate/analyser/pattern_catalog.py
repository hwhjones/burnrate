"""Public catalog and thresholds for analyser pattern signals."""

EXPLORATION_CALL_THRESHOLD = 4
SESSION_DURATION_SECONDS_THRESHOLD = 35 * 60
SESSION_WORK_TOKEN_THRESHOLD = 50_000
LARGE_OUTPUT_CHAR_THRESHOLD = 16_000
SUBAGENT_SPAWN_THRESHOLD = 6

CONTEXT_UTILIZATION_THRESHOLD = 0.80
CONTEXT_INTERVENTION_THRESHOLD = 0.90
CONTEXT_GROWTH_RUN_LENGTH = 3
CONTEXT_GROWTH_MIN_TOKENS = 4_000
CONTEXT_GROWTH_MIN_RATIO = 0.02
UNCACHED_INPUT_THRESHOLD = 20_000
CARRY_INPUT_INCREASE_THRESHOLD = 8_000
CONTEXT_SNAPSHOT_RETENTION_LIMIT = 10_000
CONTEXT_OUTPUT_EVENT_RETENTION_LIMIT = 10_000

RULE_CATALOG = {
    "R-READ-01": {"name": "Repeated file reads", "classification": "observation", "display_priority": 3, "explanation": "The same normalized file was read more than once.", "try_next_experiment": "Reference the earlier read or narrow the next read, then compare repeat counts."},
    "R-RETRY-01": {"name": "Ineffective retries", "classification": "observation", "display_priority": 1, "explanation": "The same failed command and failure fingerprint recurred consecutively.", "try_next_experiment": "Inspect the failure evidence and change one input before retrying the command."},
    "R-TEST-01": {"name": "Test churn", "classification": "observation", "display_priority": 1, "explanation": "The same test command recurred without an observed successful mutation.", "try_next_experiment": "Make or verify the smallest mutation before rerunning the same test."},
    "R-EXP-01": {"name": "Exploration calls over turn threshold", "classification": "frequency_signal", "threshold": EXPLORATION_CALL_THRESHOLD, "unit": "calls", "count_scope": "turn_occurrences", "display_priority": 3, "explanation": "At least four read or discovery calls occurred in one turn.", "try_next_experiment": "Set an exploration stop condition before the next repository sweep, then compare turn calls."},
    "R-SESSION-01": {"name": "Sessions over duration threshold", "classification": "frequency_signal", "threshold": SESSION_DURATION_SECONDS_THRESHOLD, "unit": "seconds", "count_scope": "affected_sessions", "display_priority": 4, "explanation": "The observed session duration reached 35 minutes.", "try_next_experiment": "Review the session timeline and choose a stable milestone for a fresh context."},
    "R-TOKEN-01": {"name": "Sessions over token threshold", "classification": "frequency_signal", "threshold": SESSION_WORK_TOKEN_THRESHOLD, "unit": "work_tokens", "count_scope": "affected_sessions", "display_priority": 4, "explanation": "Observed session work tokens reached 50,000.", "try_next_experiment": "Compare token usage before and after the next bounded work phase."},
    "R-OUT-01": {"name": "Tool outputs over size threshold", "classification": "frequency_signal", "threshold": LARGE_OUTPUT_CHAR_THRESHOLD, "unit": "characters", "count_scope": "direct_occurrences", "display_priority": 2, "explanation": "One observed tool result reached 16,000 characters.", "try_next_experiment": "Bound the next tool output with a range or filter, then compare follow-up input growth."},
    "R-SUBAGENT-01": {"name": "Sessions over subagent threshold", "classification": "frequency_signal", "threshold": SUBAGENT_SPAWN_THRESHOLD, "unit": "spawns", "count_scope": "affected_sessions", "display_priority": 4, "explanation": "At least six lineage-backed subagent spawns occurred in one session.", "try_next_experiment": "Review the observed subagent lineage before starting another parallel workstream."},
    "R-WEB-01": {"name": "Web-heavy session", "classification": "frequency_signal", "count_scope": "direct_occurrences", "display_priority": 4, "explanation": "Observed web search or fetch calls occurred in the session.", "try_next_experiment": "Define the question and stopping condition before the next web-call sequence."},
    "R-CTX-01": {"name": "Context pressure", "classification": "frequency_signal", "threshold": CONTEXT_UTILIZATION_THRESHOLD, "secondary_threshold": CONTEXT_INTERVENTION_THRESHOLD, "unit": "ratio", "count_scope": "model_streams", "display_priority": 2, "telemetry_required": ["input_tokens", "model_context_window"], "explanation": "Observed input tokens reached the 80% review threshold of the reported model context window; 90% is the fresh-context intervention threshold.", "try_next_experiment": "At the next stable milestone, start a fresh context and compare peak utilization."},
    "R-CTX-02": {"name": "Input-token growth", "classification": "frequency_signal", "threshold": CONTEXT_GROWTH_RUN_LENGTH, "secondary_threshold": CONTEXT_GROWTH_MIN_TOKENS, "unit": "tokens_per_snapshot", "count_scope": "growth_runs", "display_priority": 2, "telemetry_required": ["input_tokens"], "explanation": "Input tokens grew by the named minimum across consecutive observed snapshots.", "try_next_experiment": "Summarize the current state at a stable milestone, then compare subsequent input growth."},
    "R-CACHE-01": {"name": "Uncached input volume", "classification": "frequency_signal", "threshold": UNCACHED_INPUT_THRESHOLD, "unit": "tokens", "count_scope": "model_streams", "display_priority": 4, "telemetry_required": ["input_tokens", "cached_input_tokens"], "explanation": "Observed compatible counters show a high volume of uncached input tokens.", "try_next_experiment": "Review cache-compatible input counters before changing prompt or context structure."},
    "R-CARRY-01": {"name": "Temporal output-to-input relationship", "classification": "frequency_signal", "threshold": CARRY_INPUT_INCREASE_THRESHOLD, "unit": "tokens", "count_scope": "temporal_pairs", "display_priority": 2, "telemetry_required": ["output_chars", "input_tokens"], "explanation": "A large observed tool output was followed by a qualifying observed input-token increase in the same model stream; this is temporal evidence, not causal attribution.", "try_next_experiment": "Bound the next large tool output and compare the ordered follow-up input measurement."},
}

__all__ = [
    "RULE_CATALOG", "EXPLORATION_CALL_THRESHOLD", "SESSION_DURATION_SECONDS_THRESHOLD",
    "SESSION_WORK_TOKEN_THRESHOLD", "LARGE_OUTPUT_CHAR_THRESHOLD", "SUBAGENT_SPAWN_THRESHOLD",
    "CONTEXT_UTILIZATION_THRESHOLD", "CONTEXT_INTERVENTION_THRESHOLD", "CONTEXT_GROWTH_RUN_LENGTH", "CONTEXT_GROWTH_MIN_TOKENS", "CONTEXT_GROWTH_MIN_RATIO",
    "UNCACHED_INPUT_THRESHOLD", "CARRY_INPUT_INCREASE_THRESHOLD",
    "CONTEXT_SNAPSHOT_RETENTION_LIMIT", "CONTEXT_OUTPUT_EVENT_RETENTION_LIMIT",
]
