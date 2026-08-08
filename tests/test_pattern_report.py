import json
import unittest
from types import SimpleNamespace

from burnrate.analyser.pattern_report import render_json, render_text, rank_patterns


def result(rule_id, name, *, count, sessions, scope="direct_occurrences", experiment="Try it"):
    return {
        "id": rule_id,
        "name": name,
        "classification": "observation",
        "count_scope": scope,
        "count": count,
        "affected_sessions": sessions,
        "explanation": "Observed sequence.",
        "try_next_experiment": experiment,
        "examples": [{"filepath": "session.jsonl", "line": 4}],
    }


def scan(*, sessions=4, diagnostics=None, status="complete"):
    return SimpleNamespace(
        status=status,
        sessions=[object() for _ in range(sessions)],
        files_scanned=2,
        malformed_records=0,
        diagnostics=diagnostics or {},
    )


class PatternReportTests(unittest.TestCase):
    def test_priority_tiers_beat_raw_counts_and_ties_are_deterministic(self):
        results = [
            result("R-WEB-01", "Web-heavy session", count=99, sessions=9),
            result("R-TEST-01", "Test churn", count=1, sessions=1),
            result("R-RETRY-01", "Ineffective retries", count=1, sessions=1),
        ]
        self.assertEqual(
            [item["id"] for item in rank_patterns(results)],
            ["R-RETRY-01", "R-TEST-01", "R-WEB-01"],
        )

    def test_default_text_is_coached_and_capped(self):
        results = [
            result("R-RETRY-01", "Ineffective retries", count=1, sessions=1),
            result("R-TEST-01", "Test churn", count=2, sessions=2),
            result("R-READ-01", "Repeated file reads", count=3, sessions=3),
            result("R-WEB-01", "Web-heavy session", count=20, sessions=4),
        ]
        text = render_text(results, scan=scan(), window_days=20)
        self.assertIn("Top 3 signals", text)
        self.assertIn("Try:", text)
        self.assertIn("3 more raw signals: burnrate patterns --explain", text)
        self.assertIn("3 repeated reads across 3 sessions.", text)
        self.assertIn("Top 3 signals", text)

    def test_explain_shows_all_patterns_details_and_each_experiment(self):
        results = [
            result("R-RETRY-01", "Ineffective retries", count=1, sessions=1),
            result("R-READ-01", "Repeated file reads", count=2, sessions=1,
                   experiment="Reference the earlier read."),
            result("R-WEB-01", "Web-heavy session", count=3, sessions=2),
            result("R-TEST-01", "Test churn", count=4, sessions=2),
        ]
        text = render_text(results, scan=scan(), explain=True)
        self.assertIn("Web-heavy session", text)
        self.assertIn("R-RETRY-01", text)
        self.assertIn("Experiment for Repeated file reads", text)
        self.assertEqual(text.count("Experiment for "), 4)
        self.assertIn("threshold: n/a", text)

    def test_json_is_complete_versioned_and_deterministic(self):
        results = [
            result("R-WEB-01", "Web-heavy session", count=2, sessions=1),
            result("R-RETRY-01", "Ineffective retries", count=1, sessions=1),
        ]
        diagnostics = {
            "frequency_turn_coverage_missing": 1,
            "context_snapshots": 0,
        }
        first = render_json(results, scan=scan(diagnostics=diagnostics), window_days=7)
        second = render_json(results, scan=scan(diagnostics=diagnostics), window_days=7)
        self.assertEqual(first, second)
        payload = json.loads(first)
        self.assertEqual(payload["schema_version"], 3)
        self.assertEqual(payload["totals"]["rule_matches"], 3)
        self.assertEqual(len(payload["patterns"]), 2)
        self.assertEqual(payload["presentation"]["primary_pattern_id"], "R-RETRY-01")
        self.assertEqual(payload["scan"]["telemetry_coverage"]["turn"]["missing_sessions"], 1)

    def test_zero_report_is_valid_and_coverage_caveat_is_not_a_finding(self):
        text = render_text([], scan=scan(diagnostics={"context_snapshots": 0}), window_days=20)
        self.assertIn("No qualifying patterns were observed.", text)
        self.assertIn("Coverage: context: no snapshots.", text)
        self.assertIn("not measured waste", text)
        self.assertNotIn("Needs attention", text)


if __name__ == "__main__":
    unittest.main()
