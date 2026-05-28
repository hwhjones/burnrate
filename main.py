import argparse
from parsers import CodexParser, ClaudeParser

# Default locations for user session logs. These paths can be overridden by the --log-path argument.
DEFAULT_CODEX_LOG = "~/.codex/sessions/"
DEFAULT_CLAUDE_LOG = "~/.claude/projects/"

# Map parser names to parser classes for command line selection.
PARSER_MAP = {
    "codex": CodexParser,
    "claude": ClaudeParser,
}


def parse_args() -> argparse.Namespace:
    """Parse command line arguments for BurnRate."""
    # Initialize the argument parser with a description.
    parser = argparse.ArgumentParser(description="Run BurnRate log analysis.")
    parser.add_argument(
        "--parser",
        choices=PARSER_MAP,
        default="codex",
        help="Select the parser to use.",
    )
    parser.add_argument(
        "--log-path",
        default=None,
        help="Path to the log file or directory to analyze.",
    )
    return parser.parse_args()


def run() -> None:
    """Execute analysis using the selected parser and print a summary."""
    args = parse_args()
    parser_cls = PARSER_MAP[args.parser]
    log_path = args.log_path

    # Determine the log path: use the provided argument or fall back to parser-specific defaults.
    if log_path is None:
        if args.parser == "codex":
            log_path = DEFAULT_CODEX_LOG
        else:
            log_path = DEFAULT_CLAUDE_LOG

    # Inform the user about the selected parser and log path.
    print(f"Running BurnRate Analysis with parser={args.parser} log_path={log_path}")

    # Instantiate the selected parser and run the analysis flow.
    parser = parser_cls(log_path=log_path)
    parser.parse()
    parser.summary()


if __name__ == "__main__":
    run()
