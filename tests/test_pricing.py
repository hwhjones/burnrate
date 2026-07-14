import unittest
from datetime import date

from burnrate.pricing import (
    CLAUDE_PRICING,
    CLAUDE_PRICING_METADATA,
    CODEX_PRICING,
    CODEX_PRICING_METADATA,
    calculate_cost,
)


class TestPricing(unittest.TestCase):

    REQUIRED_METADATA_FIELDS = {
        "source_url",
        "currency",
        "source_unit",
        "stored_unit",
        "verified_on",
        "effective_date",
        "effective_date_status",
    }

    EXPECTED_RATES_PER_MILLION = {
        "codex": {
            "gpt-5.6": {
                "input": 5.0,
                "output": 30.0,
                "cache_read": 0.5,
                "cache_write": 6.25,
            },
            "gpt-5.6-sol": {
                "input": 5.0,
                "output": 30.0,
                "cache_read": 0.5,
                "cache_write": 6.25,
            },
            "gpt-5.6-terra": {
                "input": 2.5,
                "output": 15.0,
                "cache_read": 0.25,
                "cache_write": 3.125,
            },
            "gpt-5.6-luna": {
                "input": 1.0,
                "output": 6.0,
                "cache_read": 0.1,
                "cache_write": 1.25,
            },
            "gpt-5.5": {"input": 5.0, "output": 30.0, "cache_read": 0.5},
            "gpt-5.5-pro": {"input": 30.0, "output": 180.0},
            "gpt-5.4": {"input": 2.5, "output": 15.0, "cache_read": 0.25},
            "gpt-5.4-mini": {"input": 0.75, "output": 4.5, "cache_read": 0.075},
            "gpt-5.4-nano": {"input": 0.2, "output": 1.25, "cache_read": 0.02},
            "gpt-4o": {"input": 2.5, "output": 10.0, "cache_read": 0.25},
            "gpt-4o-mini": {"input": 0.15, "output": 0.6, "cache_read": 0.075},
            "o3": {"input": 2.0, "output": 8.0, "cache_read": 0.5},
            "o4-mini": {"input": 1.1, "output": 4.4, "cache_read": 0.275},
        },
        "claude": {
            "claude-opus-4-20250514": {
                "input": 15.0,
                "output": 75.0,
                "cache_read": 1.5,
                "cache_write": 18.75,
            },
            "claude-opus-4-6": {
                "input": 5.0,
                "output": 25.0,
                "cache_read": 0.5,
                "cache_write": 6.25,
            },
            "claude-sonnet-4-20250514": {
                "input": 3.0,
                "output": 15.0,
                "cache_read": 0.3,
                "cache_write": 3.75,
            },
            "claude-sonnet-4-5-20250929": {
                "input": 3.0,
                "output": 15.0,
                "cache_read": 0.3,
                "cache_write": 3.75,
            },
            "claude-haiku-4-5-20251001": {
                "input": 1.0,
                "output": 5.0,
                "cache_read": 0.1,
                "cache_write": 1.25,
            },
        },
    }

    def test_every_supported_rate_matches_exact_per_million_fixture(self):
        """Every bundled token-category rate matches its provider rate card."""
        tables = {"codex": CODEX_PRICING, "claude": CLAUDE_PRICING}

        for provider, expected_models in self.EXPECTED_RATES_PER_MILLION.items():
            table = tables[provider]
            self.assertEqual(set(table), set(expected_models))
            for model, expected_rates in expected_models.items():
                self.assertEqual(set(table[model]), set(expected_rates))
                for category, expected_cost in expected_rates.items():
                    token_counts = {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cache_read_tokens": 0,
                        "cache_write_tokens": 0,
                    }
                    token_counts[f"{category}_tokens"] = 1_000_000
                    with self.subTest(provider=provider, model=model, category=category):
                        costs = calculate_cost(table, model, **token_counts)
                        self.assertIsNotNone(costs)
                        if category in {"input", "output"}:
                            self.assertAlmostEqual(costs["total"], expected_cost)
                        else:
                            self.assertAlmostEqual(costs[category], expected_cost)
                            self.assertAlmostEqual(costs["total"], expected_cost)

    def test_every_priced_model_has_complete_provider_metadata(self):
        """Every priced model is covered by complete, consistently formatted provenance."""
        providers = {
            "codex": (CODEX_PRICING, CODEX_PRICING_METADATA),
            "claude": (CLAUDE_PRICING, CLAUDE_PRICING_METADATA),
        }

        for provider, (pricing, metadata) in providers.items():
            for model in pricing:
                with self.subTest(provider=provider, model=model):
                    self.assertEqual(set(metadata), self.REQUIRED_METADATA_FIELDS)
                    self.assertTrue(metadata["source_url"].startswith("https://"))
                    self.assertEqual(metadata["currency"], "USD")
                    self.assertEqual(metadata["source_unit"], "per_million_tokens")
                    self.assertEqual(metadata["stored_unit"], "per_token")
                    date.fromisoformat(metadata["verified_on"])

                    status = metadata["effective_date_status"]
                    self.assertIn(status, {"published", "unknown"})
                    if status == "published":
                        date.fromisoformat(metadata["effective_date"])
                    else:
                        self.assertIsNone(metadata["effective_date"])

    def test_codex_cost_includes_input_output_and_cache_read(self):
        """Shared pricing calculates every supported Codex token category."""
        rates = CODEX_PRICING["gpt-5.5"]
        costs = calculate_cost(
            CODEX_PRICING,
            "gpt-5.5",
            input_tokens=200,
            output_tokens=30,
            cache_read_tokens=800,
        )

        expected_cache = 800 * rates["cache_read"]
        expected_total = (
            200 * rates["input"]
            + 30 * rates["output"]
            + expected_cache
        )
        self.assertAlmostEqual(costs["cache_read"], expected_cache)
        self.assertEqual(costs["cache_write"], 0.0)
        self.assertAlmostEqual(costs["total"], expected_total)

    def test_claude_cost_includes_both_cache_categories(self):
        """Shared pricing calculates Claude cache-read and cache-write costs."""
        model = "claude-sonnet-4-5-20250929"
        rates = CLAUDE_PRICING[model]
        costs = calculate_cost(
            CLAUDE_PRICING,
            model,
            input_tokens=100,
            output_tokens=20,
            cache_read_tokens=40,
            cache_write_tokens=10,
        )

        expected_read = 40 * rates["cache_read"]
        expected_write = 10 * rates["cache_write"]
        expected_total = (
            100 * rates["input"]
            + 20 * rates["output"]
            + expected_read
            + expected_write
        )
        self.assertAlmostEqual(costs["cache_read"], expected_read)
        self.assertAlmostEqual(costs["cache_write"], expected_write)
        self.assertAlmostEqual(costs["total"], expected_total)

    def test_unknown_model_is_unpriced(self):
        """Shared pricing returns None instead of guessing an unknown rate."""
        self.assertIsNone(
            calculate_cost(
                CODEX_PRICING,
                "unknown-model",
                input_tokens=100,
                output_tokens=20,
            )
        )

    def test_unpublished_cache_category_is_unpriced(self):
        """A nonzero token category without an explicit rate is unpriced."""
        self.assertIsNone(
            calculate_cost(
                CODEX_PRICING,
                "gpt-5.5-pro",
                input_tokens=100,
                output_tokens=20,
                cache_read_tokens=1,
            )
        )
        self.assertIsNone(
            calculate_cost(
                CODEX_PRICING,
                "gpt-5.5",
                input_tokens=100,
                output_tokens=20,
                cache_write_tokens=1,
            )
        )


if __name__ == "__main__":
    unittest.main()
