"""Privacy-safe context snapshot normalization and signal detection."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .pattern_catalog import (
    CARRY_INPUT_INCREASE_THRESHOLD,
    CONTEXT_GROWTH_MIN_TOKENS,
    CONTEXT_GROWTH_MIN_RATIO,
    CONTEXT_GROWTH_RUN_LENGTH,
    CONTEXT_UTILIZATION_THRESHOLD,
    LARGE_OUTPUT_CHAR_THRESHOLD,
    UNCACHED_INPUT_THRESHOLD,
)


@dataclass(slots=True)
class ContextSnapshot:
    session_id: str
    sequence: int
    filepath: str
    line: int
    timestamp: str | None
    model_id: str | None
    context_window_tokens: int | None
    input_tokens: int | None
    cached_input_tokens: int | None
    cache_compatible: bool
    cache_write_input_tokens: int | None
    output_tokens: int | None
    reasoning_output_tokens: int | None
    total_tokens: int | None
    stream_epoch: int = 0

    @property
    def stream_key(self) -> tuple[str, int]:
        return self.session_id, self.stream_epoch


@dataclass(slots=True)
class ToolOutputEvent:
    session_id: str
    sequence: int
    filepath: str
    line: int
    timestamp: str | None
    output_chars: int
    model_id: str | None = None
    stream_epoch: int = 0

    @property
    def stream_key(self) -> tuple[str, int]:
        return self.session_id, self.stream_epoch


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _first_int(sources: tuple[dict[str, Any], ...], *keys: str) -> int | None:
    for source in sources:
        for key in keys:
            value = _int(source.get(key))
            if value is not None:
                return value
    return None


def normalize_token_snapshot(record: dict[str, Any], payload: dict[str, Any], session_id: str,
                             sequence: int, filepath: str, line: int,
                             timestamp: str | None, model_id_override: str | None = None,
                             stream_epoch: int = 0) -> ContextSnapshot | None:
    if payload.get("type") != "token_count":
        return None
    info = payload.get("info")
    if not isinstance(info, dict):
        return None
    last = info.get("last_token_usage")
    total = info.get("total_token_usage")
    if not isinstance(last, dict):
        last = {}
    total_usage = total if isinstance(total, dict) else {}
    model_id = model_id_override or _text(info.get("model")) or _text(payload.get("model")) or _text(record.get("model"))
    context_window = _first_int((payload, info, record), "model_context_window", "context_window")
    cached = _int(last.get("cached_input_tokens"))
    input_includes_cached = payload.get("input_includes_cached", info.get("input_includes_cached"))
    cache_compatible = (
        input_includes_cached is True and cached is not None and
        _int(last.get("input_tokens")) is not None and cached <= _int(last.get("input_tokens"))
    )
    return ContextSnapshot(
        session_id=session_id,
        sequence=sequence,
        filepath=filepath,
        line=line,
        timestamp=timestamp,
        model_id=model_id,
        context_window_tokens=context_window,
        input_tokens=_int(last.get("input_tokens")),
        cached_input_tokens=cached,
        cache_compatible=cache_compatible,
        cache_write_input_tokens=_int(last.get("cache_write_input_tokens")),
        output_tokens=_int(last.get("output_tokens")),
        reasoning_output_tokens=_int(last.get("reasoning_output_tokens")),
        total_tokens=_first_int((total_usage, last), "total_tokens"),
        stream_epoch=stream_epoch,
    )


def _source(snapshot: ContextSnapshot) -> dict[str, Any]:
    return {
        "filepath": snapshot.filepath,
        "line": snapshot.line,
        "model_id": snapshot.model_id,
        "stream_epoch": snapshot.stream_epoch,
    }


def _occurrence(rule_id: str, session_id: str, sequence: int, example: dict[str, Any]) -> dict[str, Any]:
    return {"rule_id": rule_id, "session_id": session_id, "sequence": sequence, "example": example}


def detect_context_signals(session: Any) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Detect context signals from numeric snapshots and output event positions."""
    snapshots: list[ContextSnapshot] = sorted(session.context_snapshots, key=lambda item: item.sequence)
    outputs: list[ToolOutputEvent] = sorted(session.tool_output_events, key=lambda item: item.sequence)
    by_stream: dict[tuple[str, str], list[ContextSnapshot]] = {}
    for snapshot in snapshots:
        by_stream.setdefault(snapshot.stream_key, []).append(snapshot)

    occurrences: list[dict[str, Any]] = []
    diagnostics = {
        "context_snapshots": len(snapshots),
        "context_missing_window": 0,
        "context_missing_input": 0,
        "context_model_streams": len(by_stream),
        "context_growth_resets": 0,
        "context_cache_unavailable": 0,
        "context_carry_unavailable": 0,
    }

    for stream_key, stream in by_stream.items():
        usable = [item for item in stream if item.input_tokens is not None]
        diagnostics["context_missing_input"] += sum(item.input_tokens is None for item in stream)
        diagnostics["context_missing_window"] += sum(
            item.input_tokens is not None and item.context_window_tokens is None for item in stream
        )

        pressure = [
            (item.input_tokens / item.context_window_tokens, item)
            for item in usable
            if item.context_window_tokens and item.context_window_tokens > 0
        ]
        if pressure:
            peak_ratio, peak = max(pressure, key=lambda pair: (pair[0], pair[1].sequence))
            if peak_ratio >= CONTEXT_UTILIZATION_THRESHOLD:
                occurrences.append(_occurrence(
                    "R-CTX-01", session.session_id, peak.sequence,
                    {**_source(peak), "measured_value": peak_ratio, "unit": "ratio",
                     "threshold": CONTEXT_UTILIZATION_THRESHOLD, "telemetry_available": True,
                     "input_tokens": peak.input_tokens, "context_window_tokens": peak.context_window_tokens},
                ))

        run = 0
        previous: ContextSnapshot | None = None
        for snapshot in stream:
            if snapshot.input_tokens is None:
                run = 0
                previous = None
                diagnostics["context_growth_resets"] += 1
                continue
            if previous is not None:
                delta = snapshot.input_tokens - (previous.input_tokens or 0)
                growth_threshold = max(
                    CONTEXT_GROWTH_MIN_TOKENS,
                    math.ceil((snapshot.context_window_tokens or 0) * CONTEXT_GROWTH_MIN_RATIO),
                )
                if delta >= growth_threshold:
                    run += 1
                    if run == CONTEXT_GROWTH_RUN_LENGTH:
                        occurrences.append(_occurrence(
                            "R-CTX-02", session.session_id, snapshot.sequence,
                            {**_source(snapshot), "measured_value": delta, "unit": "tokens_per_snapshot",
                             "threshold": CONTEXT_GROWTH_RUN_LENGTH,
                             "secondary_threshold": growth_threshold,
                             "run_length": run, "telemetry_available": True},
                        ))
                else:
                    run = 0
                    diagnostics["context_growth_resets"] += 1
            previous = snapshot

        cache_values = [
            (max(0, item.input_tokens - item.cached_input_tokens), item)
            for item in usable
            if item.cache_compatible and item.cached_input_tokens is not None
        ]
        if not cache_values:
            diagnostics["context_cache_unavailable"] += 1
        else:
            uncached, peak = max(cache_values, key=lambda pair: (pair[0], pair[1].sequence))
            if uncached >= UNCACHED_INPUT_THRESHOLD:
                occurrences.append(_occurrence(
                    "R-CACHE-01", session.session_id, peak.sequence,
                    {**_source(peak), "measured_value": uncached, "unit": "tokens",
                     "threshold": UNCACHED_INPUT_THRESHOLD, "telemetry_available": True,
                     "input_tokens": peak.input_tokens, "cached_input_tokens": peak.cached_input_tokens},
                ))

        stream_outputs = [item for item in outputs if item.stream_key == stream_key]
        for output in stream_outputs:
            if output.output_chars < LARGE_OUTPUT_CHAR_THRESHOLD:
                continue
            active_before_output = [
                item for item in snapshots
                if item.sequence <= output.sequence and item.input_tokens is not None
            ]
            if not active_before_output or active_before_output[-1].stream_key != stream_key:
                continue
            prior: ContextSnapshot | None = None
            for snapshot in stream:
                if snapshot.sequence <= output.sequence:
                    if snapshot.input_tokens is not None:
                        prior = snapshot
                    continue
                if prior is None or prior.input_tokens is None or snapshot.input_tokens is None:
                    continue
                increase = snapshot.input_tokens - prior.input_tokens
                if increase >= CARRY_INPUT_INCREASE_THRESHOLD:
                    occurrences.append(_occurrence(
                        "R-CARRY-01", session.session_id, snapshot.sequence,
                        {"filepath": output.filepath, "line": output.line,
                         "model_id": snapshot.model_id, "stream_epoch": snapshot.stream_epoch,
                         "followup_filepath": snapshot.filepath, "followup_line": snapshot.line,
                         "followup_model_id": snapshot.model_id,
                         "followup_stream_epoch": snapshot.stream_epoch,
                         "measured_value": increase, "unit": "tokens",
                         "threshold": CARRY_INPUT_INCREASE_THRESHOLD,
                         "output_characters": output.output_chars,
                         "telemetry_available": True, "relationship": "temporal"},
                    ))
                    break
                prior = snapshot
            else:
                diagnostics["context_carry_unavailable"] += 1

    return occurrences, diagnostics
