"""SIPL interpreter: executes an AST over a state and emits events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping

from .. import ast as A
from ..parser import parse
from ..source import Diagnostic, SourceSpan
from .events import (AfterStatement, BeforeStatement, ConditionEvaluated,
                     Event, Finished, VariableChanged)

DEFAULT_MAX_STEPS = 100_000


class SiplRuntimeError(Exception):
    def __init__(self, code: str, message: str, span: SourceSpan | None):
        super().__init__(message)
        self.diagnostic = Diagnostic("error", code, message, span)


# ------------------------------------------------------------ expressions

def eval_arith(e: A.Arith, st: Mapping[str, int]) -> int:
    if isinstance(e, A.Num):
        return e.value
    if isinstance(e, A.Var):
        try:
            return st[e.name]
        except KeyError:
            raise SiplRuntimeError(
                "RT-UNDEFINED-VAR",
                f"variable '{e.name}' has no value in the current state "
                f"(provide it with --state {e.name}=<n>)", e.span) from None
    if isinstance(e, A.Neg):
        return -eval_arith(e.operand, st)
    a, b = eval_arith(e.left, st), eval_arith(e.right, st)
    op = e.op
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if b == 0:
        raise SiplRuntimeError("RT-DIV-ZERO", f"'{op}' by zero", e.span)
    return a // b if op == "div" else a % b


_CMP = {"=": lambda a, b: a == b, "<>": lambda a, b: a != b,
        "<": lambda a, b: a < b, "<=": lambda a, b: a <= b,
        ">": lambda a, b: a > b, ">=": lambda a, b: a >= b}


def eval_cond(c: A.Cond, st: Mapping[str, int]) -> bool:
    if isinstance(c, A.BoolLit):
        return c.value
    if isinstance(c, A.Compare):
        return _CMP[c.op](eval_arith(c.left, st), eval_arith(c.right, st))
    if isinstance(c, A.Not):
        return not eval_cond(c.operand, st)
    if c.op == "and":     # short-circuit: right side is not evaluated if left is false
        return eval_cond(c.left, st) and eval_cond(c.right, st)
    return eval_cond(c.left, st) or eval_cond(c.right, st)


# ------------------------------------------------------------ interpreter

@dataclass
class RunResult:
    status: str                       # "terminated" | "error"
    state: dict[str, int]
    steps: int
    error: Diagnostic | None = None
    events: list[Event] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "terminated"

    def to_dict(self, with_events: bool = False) -> dict:
        d = {"status": self.status, "state": dict(sorted(self.state.items())),
             "steps": self.steps,
             "error": self.error.to_dict() if self.error else None}
        if with_events:
            d["events"] = [e.to_dict() for e in self.events]
        return d


class Interpreter:
    def __init__(self, program: A.Program, *, max_steps: int = DEFAULT_MAX_STEPS,
                 detect_loops: bool = True,
                 observer: Callable[[Event], None] | None = None):
        self.program = program
        self.max_steps = max_steps
        self.detect_loops = detect_loops
        self.observer = observer
        self.state: dict[str, int] = {}
        self.steps = 0
        self._seq = 0
        self._seen: set[tuple] = set()

    def _emit(self, cls, span=None, **kw) -> None:
        if self.observer is None:
            self._seq += 1
            return
        ev = cls(seq=self._seq, step=self.steps, state=dict(self.state), span=span, **kw)
        self._seq += 1
        self.observer(ev)

    def run(self, initial: Mapping[str, int] | None = None) -> RunResult:
        self.state = dict(initial or {})
        self.steps = 0
        self._seq = 0
        self._seen = set()
        error: Diagnostic | None = None
        try:
            self._exec(self.program.body)
        except SiplRuntimeError as e:
            error = e.diagnostic
        status = "error" if error else "terminated"
        self._emit(Finished, error.span if error else None, status=status,
                   error=error.to_dict() if error else None)
        return RunResult(status, dict(self.state), self.steps, error)

    # -- statements
    def _exec(self, s: A.Stmt) -> None:
        if isinstance(s, A.Seq):
            for x in s.statements:
                self._exec(x)
            return
        if isinstance(s, A.Block):
            self._exec(s.body)
            return
        self.steps += 1
        if self.steps > self.max_steps:
            raise SiplRuntimeError(
                "RT-STEP-LIMIT",
                f"step limit exceeded ({self.max_steps} statements); "
                f"the program may not terminate (raise it with --max-steps)", s.span)
        kind = type(s).__name__
        self._emit(BeforeStatement, s.span, stmt=kind, text=_head(s))
        if isinstance(s, A.Skip):
            pass
        elif isinstance(s, A.Assign):
            new = eval_arith(s.value, self.state)
            old = self.state.get(s.target)
            self.state[s.target] = new
            self._emit(VariableChanged, s.target_span or s.span,
                       name=s.target, old=old, new=new)
        elif isinstance(s, A.If):
            value = eval_cond(s.cond, self.state)
            self._emit(ConditionEvaluated, s.cond.span, context="if",
                       text=A.cond_to_str(s.cond), value=value)
            branch = s.then if value else s.orelse
            if branch is not None:
                self._exec(branch)
        else:  # While
            while True:
                value = eval_cond(s.cond, self.state)
                self._emit(ConditionEvaluated, s.cond.span, context="while",
                           text=A.cond_to_str(s.cond), value=value)
                if not value:
                    break
                if self.detect_loops:
                    key = (s.span.start, tuple(sorted(self.state.items())))
                    if key in self._seen:
                        raise SiplRuntimeError(
                            "RT-INFINITE-LOOP",
                            "infinite loop: the same state was reached again at this "
                            "'while' (the program never terminates)", s.span)
                    self._seen.add(key)
                self._exec(s.body)
        self._emit(AfterStatement, s.span, stmt=kind)


def _head(s: A.Stmt) -> str:
    if isinstance(s, A.Assign):
        return f"{s.target} := {A.arith_to_str(s.value)}"
    if isinstance(s, A.If):
        return f"if {A.cond_to_str(s.cond)} then ..."
    if isinstance(s, A.While):
        return f"while {A.cond_to_str(s.cond)} do ..."
    return "skip"


def _as_program(program: "A.Program | str", extensions: bool = False) -> A.Program:
    return parse(program, extensions) if isinstance(program, str) else program


def run(program: "A.Program | str", state: Mapping[str, int] | None = None, *,
        max_steps: int = DEFAULT_MAX_STEPS, detect_loops: bool = True,
        extensions: bool = False) -> RunResult:
    """Execute a program (AST or source text). Runtime failures are reported in the result."""
    return Interpreter(_as_program(program, extensions), max_steps=max_steps,
                       detect_loops=detect_loops).run(state)


def trace(program: "A.Program | str", state: Mapping[str, int] | None = None, *,
          max_steps: int = DEFAULT_MAX_STEPS, detect_loops: bool = True,
          extensions: bool = False) -> RunResult:
    """Like :func:`run` but ``result.events`` holds the full event trace."""
    events: list[Event] = []
    res = Interpreter(_as_program(program, extensions), max_steps=max_steps,
                      detect_loops=detect_loops, observer=events.append).run(state)
    res.events = events
    return res
