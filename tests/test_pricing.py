import unittest

from burnrate.pricing import CLAUDE_PRICING, CODEX_PRICING, calculate_cost


class TestPricing(unittest.TestCase):

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


if __name__ == "__main__":
    unittest.main()
