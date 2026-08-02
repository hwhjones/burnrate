"""Experimental structured trace readers.

These readers are intentionally separate from the stable usage and cost
parsers.  They retain only the structured evidence required by their pilots.
"""

from .codex import CodexTraceReader
from .normalize import CodexTraceNormalizer, normalize_events
from .waste import CodexWasteAnalyzer
from .correlation import BOUNDARY_RULES, SIMILARITY_LADDER, correlate_messages, segment_episodes
from .catalog import CATALOG_RULES, CATALOG_SCHEMA, review_coverage, tune_thresholds, compute_baselines, lower_signal_candidates

__all__ = ["CodexTraceReader", "CodexTraceNormalizer", "CodexWasteAnalyzer", "normalize_events", "BOUNDARY_RULES", "SIMILARITY_LADDER", "correlate_messages", "segment_episodes", "CATALOG_RULES", "CATALOG_SCHEMA", "review_coverage", "tune_thresholds", "compute_baselines", "lower_signal_candidates"]
