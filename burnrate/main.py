import argparse
import sys
from datetime import datetime, timedelta, timezone
from .parsers import CodexParser, ClaudeParser
from .analyser.patterns import PatternReader, detect_observations
from .analyser.pattern_report import render_json, render_text

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
        "command",
        nargs="?",
        choices=("patterns",),
        help="Run the workflow pattern report.",
    )
    parser.add_argument(
        "--patterns",
        action="store_true",
        help="Run the workflow pattern report (compatibility form).",
    )
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
    parser.add_argument("--days", type=int, default=7, help="Pattern scan window in days (default: 7).")
    parser.add_argument("--json", action="store_true", help="Render a complete deterministic JSON report.")
    parser.add_argument("--explain", action="store_true", help="Show thresholds, telemetry, and source references.")
    args = parser.parse_args()
    pattern_mode = args.patterns or args.command == "patterns"
    if args.days <= 0:
        parser.error("--days must be a positive integer")
    if (args.json or args.explain or args.days != 7) and not pattern_mode:
        parser.error("--days, --json, and --explain require --patterns or the patterns command")
    if pattern_mode and args.parser != "codex":
        parser.error("workflow patterns currently support only --parser codex")
    args.pattern_mode = pattern_mode
    return args


def _filter_pattern_window(scan, days: int) -> None:
    """Keep sessions whose observed activity intersects the requested window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    selected = []
    for session in scan.sessions:
        timestamp = session.last_timestamp or session.first_timestamp
        if not timestamp:
            continue
        try:
            observed = datetime.fromisoformat(timestamp)
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if observed >= cutoff:
            selected.append(session)
    scan.sessions = selected


def _run_patterns(args: argparse.Namespace) -> int:
    log_path = args.log_path or DEFAULT_CODEX_LOG
    scan = PatternReader(log_path=log_path).scan()
    if scan.status not in {"invalid", "empty"}:
        _filter_pattern_window(scan, args.days)
    results = detect_observations(scan) if scan.status not in {"invalid", "empty"} else []
    path_hint = f' --log-path "{args.log_path}"' if args.log_path else ""
    explain_command = f"burnrate patterns --days {args.days}{path_hint} --explain"
    rerun_command = f"burnrate patterns --days 7{path_hint}"
    if args.json:
        print(render_json(results, scan=scan, window_days=args.days,
                          explain_command=explain_command, rerun_command=rerun_command), end="")
    else:
        print(render_text(results, scan=scan, window_days=args.days, explain=args.explain,
                          explain_command=explain_command, rerun_command=rerun_command,
                          color=bool(getattr(sys.stdout, "isatty", lambda: False)())), end="")
    if scan.status == "invalid":
        return 2
    if scan.status == "partial":
        return 1
    return 0


def run() -> int:
    """Execute the analysis and return a process-compatible status code."""
    args = parse_args()
    if args.pattern_mode:
        return _run_patterns(args)
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

    if parser.invalid_input_path:
        return 2
    if parser.scan_incomplete:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
