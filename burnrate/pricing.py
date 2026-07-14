"""Shared model pricing tables and cost calculations."""

CODEX_PRICING_METADATA = {
    "source_url": "https://developers.openai.com/api/docs/pricing",
    "currency": "USD",
    "source_unit": "per_million_tokens",
    "stored_unit": "per_token",
    "verified_on": "2026-07-14",
    "effective_date": None,
    "effective_date_status": "unknown",
}

CLAUDE_PRICING_METADATA = {
    "source_url": (
        "https://www-cdn.anthropic.com/files/4zrzovbb/website/"
        "3684c2faafb97418665782cea0001f439f74b1d2.pdf"
    ),
    "currency": "USD",
    "source_unit": "per_million_tokens",
    "stored_unit": "per_token",
    "verified_on": "2026-07-14",
    "effective_date": "2026-05-27",
    "effective_date_status": "published",
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
        "input": 0.0000025,
        "output": 0.000015,
        "cache_read": 0.00000025,
        "cache_write": 0.000003125,
    },
    "gpt-5.6-luna": {
        "input": 0.000001,
        "output": 0.000006,
        "cache_read": 0.0000001,
        "cache_write": 0.00000125,
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
