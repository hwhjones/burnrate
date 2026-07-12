"""Shared model pricing tables and cost calculations."""

CODEX_PRICING = {
    "gpt-5.5": {
        "input": 0.000005,
        "output": 0.000030,
        "cache_read": 0.0000005,
        "cache_write": 0.000006250,
    },
    "gpt-5.5-pro": {
        "input": 0.000030,
        "output": 0.000180,
        "cache_read": 0.000003,
        "cache_write": 0.0000375,
    },
    "gpt-5.4": {
        "input": 0.0000025,
        "output": 0.000015,
        "cache_read": 0.00000025,
        "cache_write": 0.000003125,
    },
    "gpt-5.4-mini": {
        "input": 0.0000005,
        "output": 0.000002,
        "cache_read": 0.00000005,
        "cache_write": 0.000000625,
    },
    "gpt-5.4-nano": {
        "input": 0.0000001,
        "output": 0.0000004,
        "cache_read": 0.00000001,
        "cache_write": 0.000000125,
    },
    "gpt-4o": {
        "input": 0.0000025,
        "output": 0.00001,
        "cache_read": 0.00000025,
        "cache_write": 0.000003125,
    },
    "gpt-4o-mini": {
        "input": 0.00000015,
        "output": 0.0000006,
        "cache_read": 0.000000015,
        "cache_write": 0.0000001875,
    },
    "o3": {
        "input": 0.00001,
        "output": 0.00004,
        "cache_read": 0.000001,
        "cache_write": 0.0000125,
    },
    "o4-mini": {
        "input": 0.000003,
        "output": 0.000012,
        "cache_read": 0.0000003,
        "cache_write": 0.00000375,
    },
}

CLAUDE_PRICING = {
    "claude-opus-4-20250514": {
        "input": 0.000015,
        "output": 0.000075,
        "cache_read": 0.0000015,
        "cache_write": 0.00001875,
    },
    "claude-opus-4-6": {
        "input": 0.000015,
        "output": 0.000075,
        "cache_read": 0.0000015,
        "cache_write": 0.00001875,
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
    "claude-haiku-4-5-20251001": {
        "input": 0.0000008,
        "output": 0.000004,
        "cache_read": 0.00000008,
        "cache_write": 0.000001,
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

    cache_read_cost = cache_read_tokens * rates.get(
        "cache_read", rates["input"] * 0.1
    )
    cache_write_cost = cache_write_tokens * rates.get(
        "cache_write", rates["input"] * 1.25
    )

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
