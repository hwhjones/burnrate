"""BurnRate - LLM usage log parser and cost analyzer."""

from importlib import metadata

from .main import run
from .parsers import CodexParser, ClaudeParser, BaseParser

try:
    __version__ = metadata.version("burnrate")
except metadata.PackageNotFoundError:
    __version__ = "0+unknown"
