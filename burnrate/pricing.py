"""Shared model pricing tables and cost calculations."""

CODEX_PRICING_METADATA = {
    "source_url": "https://developers.openai.com/api/docs/pricing",
    "currency": "USD",
    "source_unit": "per_million_tokens",
    "stored_unit": "per_token",
    "verified_on": "2026-08-16",
    "effective_date": None,
    "effective_date_status": "unknown",
}

CLAUDE_PRICING_METADATA = {
    "source_url": "https://platform.claude.com/docs/en/about-claude/pricing",
    "currency": "USD",
    "source_unit": "per_million_tokens",
    "stored_unit": "per_token",
    "verified_on": "2026-08-16",
    "effective_date": None,
    "effective_date_status": "unknown",
}

CODEX_PRICING = {
    "gpt-5.6": {
        "input": 0.000005,
        "output": 0.000030,
        "cache_read": 0.0000005,
        "cache_write": 0.00000625,
    },
    "gpt-5.6-sol": {
        "input": 0.000005,
        "output": 0.000030,
        "cache_read": 0.0000005,
        "cache_write": 0.00000625,
    },
    "gpt-5.6-terra": {
        "input": 0.000002,
        "output": 0.000012,
        "cache_read": 0.0000002,
        "cache_write": 0.0000025,
    },
    "gpt-5.6-luna": {
        "input": 0.0000002,
        "output": 0.0000012,
        "cache_read": 0.00000002,
        "cache_write": 0.00000025,
    },
    "gpt-5.3-codex": {
        "input": 0.00000175,
        "output": 0.000014,
        "cache_read": 0.000000175,
    },
    "gpt-5.6-cyber": {
        "input": 0.0000125,
        "output": 0.000075,
        "cache_read": 0.00000125,
        "cache_write": 0.000015625,
    },
    "daybreak-blue-latest": {
        "input": 0.000005,
        "output": 0.000030,
        "cache_read": 0.0000005,
        "cache_write": 0.00000625,
    },
    "daybreak-red-latest": {
        "input": 0.0000125,
        "output": 0.000075,
        "cache_read": 0.00000125,
        "cache_write": 0.000015625,
    },
    "gpt-5.5": {
        "input": 0.000005,
        "output": 0.000030,
        "cache_read": 0.0000005,
    },
    "gpt-5.5-pro": {
        "input": 0.000030,
        "output": 0.000180,
    },
    "gpt-5.4": {
        "input": 0.0000025,
        "output": 0.000015,
        "cache_read": 0.00000025,
    },
    # Auto-review is a subscription reviewer label, not a published API SKU.
    # OpenAI's current Codex telemetry does not expose its underlying model;
    # use the observed GPT-5.4 routing as an explicitly qualified estimate.
    "codex-auto-review": {
        "input": 0.0000025,
        "output": 0.000015,
        "cache_read": 0.00000025,
    },
    "gpt-5.4-mini": {
        "input": 0.00000075,
        "output": 0.0000045,
        "cache_read": 0.000000075,
    },
    "gpt-5.4-nano": {
        "input": 0.0000002,
        "output": 0.00000125,
        "cache_read": 0.00000002,
    },
    "gpt-4o": {
        "input": 0.0000025,
        "output": 0.00001,
        "cache_read": 0.00000025,
    },
    "gpt-4o-mini": {
        "input": 0.00000015,
        "output": 0.0000006,
        "cache_read": 0.000000075,
    },
    "o3": {
        "input": 0.000002,
        "output": 0.000008,
        "cache_read": 0.0000005,
    },
    "o4-mini": {
        "input": 0.0000011,
        "output": 0.0000044,
        "cache_read": 0.000000275,
    },
}

CLAUDE_PRICING = {
    "claude-fable-5": {
        "input": 0.000010,
        "output": 0.000050,
        "cache_read": 0.000001,
        "cache_write": 0.0000125,
    },
    "claude-mythos-5": {
        "input": 0.000010,
        "output": 0.000050,
        "cache_read": 0.000001,
        "cache_write": 0.0000125,
    },
    "claude-opus-5": {
        "input": 0.000005,
        "output": 0.000025,
        "cache_read": 0.0000005,
        "cache_write": 0.00000625,
    },
    "claude-opus-4-8": {
        "input": 0.000005,
        "output": 0.000025,
        "cache_read": 0.0000005,
        "cache_write": 0.00000625,
    },
    "claude-opus-4-7": {
        "input": 0.000005,
        "output": 0.000025,
        "cache_read": 0.0000005,
        "cache_write": 0.00000625,
    },
    "claude-opus-4-20250514": {
        "input": 0.000015,
        "output": 0.000075,
        "cache_read": 0.0000015,
        "cache_write": 0.00001875,
    },
    "claude-opus-4-6": {
        "input": 0.000005,
        "output": 0.000025,
        "cache_read": 0.0000005,
        "cache_write": 0.00000625,
    },
    "claude-opus-4-5": {
        "input": 0.000005,
        "output": 0.000025,
        "cache_read": 0.0000005,
        "cache_write": 0.00000625,
    },
    "claude-opus-4-1": {
        "input": 0.000015,
        "output": 0.000075,
        "cache_read": 0.0000015,
        "cache_write": 0.00001875,
    },
    "claude-opus-4": {
        "input": 0.000015,
        "output": 0.000075,
        "cache_read": 0.0000015,
        "cache_write": 0.00001875,
    },
    "claude-opus-3": {
        "input": 0.000015,
        "output": 0.000075,
        "cache_read": 0.0000015,
        "cache_write": 0.00001875,
    },
    "claude-sonnet-5": {
        "input": 0.000002,
        "output": 0.000010,
        "cache_read": 0.0000002,
        "cache_write": 0.0000025,
    },
    "claude-sonnet-4-6": {
        "input": 0.000003,
        "output": 0.000015,
        "cache_read": 0.0000003,
        "cache_write": 0.00000375,
    },
    "claude-sonnet-4-20250514": {
        "input": 0.000003,
        "output": 0.000015,
        "cache_read": 0.0000003,
        "cache_write": 0.00000375,
    },
    "claude-sonnet-4-5-20250929": {
        "input": 0.000003,
        "output": 0.000015,
        "cache_read": 0.0000003,
        "cache_write": 0.00000375,
    },
    "claude-sonnet-4-5": {
        "input": 0.000003,
        "output": 0.000015,
        "cache_read": 0.0000003,
        "cache_write": 0.00000375,
    },
    "claude-sonnet-4": {
        "input": 0.000003,
        "output": 0.000015,
        "cache_read": 0.0000003,
        "cache_write": 0.00000375,
    },
    "claude-sonnet-3-7": {
        "input": 0.000003,
        "output": 0.000015,
        "cache_read": 0.0000003,
        "cache_write": 0.00000375,
    },
    "claude-sonnet-3-5": {
        "input": 0.000003,
        "output": 0.000015,
        "cache_read": 0.0000003,
        "cache_write": 0.00000375,
    },
    "claude-haiku-4-5": {
        "input": 0.000001,
        "output": 0.000005,
        "cache_read": 0.0000001,
        "cache_write": 0.00000125,
    },
    "claude-haiku-3-5": {
        "input": 0.0000008,
        "output": 0.000004,
        "cache_read": 0.00000008,
        "cache_write": 0.000001,
    },
    "claude-haiku-4-5-20251001": {
        "input": 0.000001,
        "output": 0.000005,
        "cache_read": 0.0000001,
        "cache_write": 0.00000125,
    },
}


def calculate_cost(
    pricing_table,
    model,
    input_tokens,
    output_tokens,
    cache_read_tokens=0,
    cache_write_tokens=0,
):
    """Return total and cache costs for a known model, or None if unpriced."""
    rates = pricing_table.get(model)
    if rates is None:
        return None

    if cache_read_tokens and "cache_read" not in rates:
        return None
    if cache_write_tokens and "cache_write" not in rates:
        return None

    cache_read_cost = cache_read_tokens * rates.get("cache_read", 0)
    cache_write_cost = cache_write_tokens * rates.get("cache_write", 0)

    return {
        "total": (
            input_tokens * rates["input"]
            + output_tokens * rates["output"]
            + cache_read_cost
            + cache_write_cost
        ),
        "cache_read": cache_read_cost,
        "cache_write": cache_write_cost,
    }
