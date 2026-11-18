"""Source positions and diagnostics shared by every SIPL component."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceSpan:
    """Half-open range [start, end) in the source text.

    ``line``/``col`` are 1-based and describe the start; ``end_line``/``end_col``
    describe the position just after the last character.
    """

    start: int
    end: int
    line: int
    col: int
    end_line: int
    end_col: int

    def to(self, other: "SourceSpan") -> "SourceSpan":
        """Smallest span covering ``self`` and ``other`` (self must start first)."""
        return SourceSpan(self.start, other.end, self.line, self.col,
                          other.end_line, other.end_col)

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end,
                "line": self.line, "col": self.col,
                "end_line": self.end_line, "end_col": self.end_col}

    def __str__(self) -> str:
        return f"{self.line}:{self.col}"


class LineIndex:
    """Converts character offsets to (line, column)."""

    def __init__(self, text: str):
        self.text = text
        self._starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                self._starts.append(i + 1)

    def position(self, offset: int) -> tuple[int, int]:
        lo, hi = 0, len(self._starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1, offset - self._starts[lo] + 1

    def span(self, start: int, end: int) -> SourceSpan:
        line, col = self.position(start)
        end_line, end_col = self.position(end)
        return SourceSpan(start, end, line, col, end_line, end_col)


@dataclass(frozen=True)
class Diagnostic:
    """A user-facing problem. ``code`` is stable and machine-readable."""

    severity: str            # "error" | "warning" | "info"
    code: str                # e.g. "SYN-UNEXPECTED-TOKEN", "RT-DIV-ZERO"
    message: str
    span: SourceSpan | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "code": self.code,
                "message": self.message,
                "span": self.span.to_dict() if self.span else None}

    def format(self, filename: str = "<input>") -> str:
        where = f"{filename}:{self.span}" if self.span else filename
        return f"{where}: {self.severity}[{self.code}]: {self.message}"
