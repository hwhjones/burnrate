import argparse
from parsers import CodexParser, ClaudeParser

DEFAULT_CODEX_LOG = "~/.codex/sessions/"
DEFAULT_CLAUDE_LOG = "~/.claude/sessions/"
PARSER_MAP = {
    "codex": CodexParser,
    "claude": ClaudeParser,
}


def parse_args() -> argparse.Namespace:
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
        help="Path to the log file to analyze.",
    )
    return parser.parse_args()


def run() -> None:
    args = parse_args()
    parser_cls = PARSER_MAP[args.parser]
    log_path = args.log_path

    if log_path is None:
        if args.parser == "codex":
            log_path = DEFAULT_CODEX_LOG
        else:
            log_path = DEFAULT_CLAUDE_LOG

    print(f"Running BurnRate Analysis with parser={args.parser} log_path={log_path}")
    parser = parser_cls(log_path=log_path)
    parser.parse()
    parser.summary()


if __name__ == "__main__":
    run()
