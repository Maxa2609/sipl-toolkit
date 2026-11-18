"""SIPL Language Toolkit: shared core (parser, AST, interpreter, semantic terms)."""

from .source import Diagnostic, SourceSpan
from .parser import parse, check, SiplSyntaxError
from .interpreter import run, trace, RunResult
from .semantics import build_term, evaluate_term, format_term

__version__ = "0.6.3"

__all__ = [
    "Diagnostic", "SourceSpan", "parse", "check", "SiplSyntaxError",
    "run", "trace", "RunResult", "build_term", "evaluate_term", "format_term",
    "__version__",
]
