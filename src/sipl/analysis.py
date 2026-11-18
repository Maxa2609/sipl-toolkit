"""Small static analyses shared by the CLI and IDE tools."""

from __future__ import annotations

from . import ast as A


def _flow(s: A.Stmt, defined: frozenset[str]) -> tuple[set[str], frozenset[str]]:
    """Returns (variables read before being surely assigned, surely-assigned after ``s``)."""
    if isinstance(s, A.Skip):
        return set(), defined
    if isinstance(s, A.Assign):
        return A.free_variables(s.value) - defined, defined | {s.target}
    if isinstance(s, A.Block):
        return _flow(s.body, defined)
    if isinstance(s, A.Seq):
        reads: set[str] = set()
        for x in s.statements:
            r, defined = _flow(x, defined)
            reads |= r
        return reads, defined
    if isinstance(s, A.If):
        reads = A.free_variables(s.cond) - defined
        r1, d1 = _flow(s.then, defined)
        r2, d2 = _flow(s.orelse, defined) if s.orelse is not None else (set(), defined)
        return reads | r1 | r2, d1 & d2
    if isinstance(s, A.While):
        reads = A.free_variables(s.cond) - defined
        r, _ = _flow(s.body, defined)
        return reads | r, defined          # the body may execute zero times
    raise TypeError(s)


def input_variables(program: A.Program) -> list[str]:
    """Variables that may be read before any assignment: they must come from the initial state."""
    reads, _ = _flow(program.body, frozenset())
    return sorted(reads)
