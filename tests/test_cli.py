import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import Mock, patch

import burnrate.main as cli


class TestCLI(unittest.TestCase):

    def _run_with_mock_parsers(self, arguments):
        """Run the CLI with isolated parser classes and return their mocks."""
        codex_instance = Mock()
        claude_instance = Mock()
        codex_parser = Mock(return_value=codex_instance)
        claude_parser = Mock(return_value=claude_instance)

        parser_map = {"codex": codex_parser, "claude": claude_parser}
        with patch.dict(cli.PARSER_MAP, parser_map, clear=True):
            with patch("sys.argv", ["burnrate", *arguments]):
                with redirect_stdout(StringIO()):
                    cli.run()

        return codex_parser, codex_instance, claude_parser, claude_instance

    def test_default_command_runs_codex_parser(self):
        """CLI defaults to Codex and runs parse followed by summary."""
        codex_parser, codex, claude_parser, _ = self._run_with_mock_parsers([])

        codex_parser.assert_called_once_with(log_path=cli.DEFAULT_CODEX_LOG)
        codex.parse.assert_called_once_with()
        codex.summary.assert_called_once_with()
        claude_parser.assert_not_called()

    def test_claude_option_runs_claude_parser(self):
        """CLI selects Claude and supplies its default log directory."""
        codex_parser, _, claude_parser, claude = self._run_with_mock_parsers(
            ["--parser", "claude"]
        )

        claude_parser.assert_called_once_with(log_path=cli.DEFAULT_CLAUDE_LOG)
        claude.parse.assert_called_once_with()
        claude.summary.assert_called_once_with()
        codex_parser.assert_not_called()

    def test_custom_log_path_overrides_default(self):
        """CLI passes an explicit log path to the selected parser unchanged."""
        custom_path = r"C:\logs\codex"
        codex_parser, codex, _, _ = self._run_with_mock_parsers(
            ["--parser", "codex", "--log-path", custom_path]
        )

        codex_parser.assert_called_once_with(log_path=custom_path)
        codex.parse.assert_called_once_with()
        codex.summary.assert_called_once_with()

    def test_invalid_parser_is_rejected(self):
        """CLI rejects parser names that are not registered."""
        with patch("sys.argv", ["burnrate", "--parser", "unknown"]):
            with redirect_stderr(StringIO()) as error_output:
                with self.assertRaises(SystemExit) as raised:
                    cli.parse_args()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("invalid choice", error_output.getvalue())

    def test_help_lists_available_options(self):
        """CLI help exits successfully and documents parsers and log paths."""
        with patch("sys.argv", ["burnrate", "--help"]):
            with redirect_stdout(StringIO()) as help_output:
                with self.assertRaises(SystemExit) as raised:
                    cli.parse_args()

        output = help_output.getvalue()
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("--parser", output)
        self.assertIn("--log-path", output)
        self.assertIn("codex", output)
        self.assertIn("claude", output)


if __name__ == "__main__":
    unittest.main()
