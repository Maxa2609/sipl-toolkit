"""SEM-02: evaluate a semantic term on a state, recording the rules applied.

The evaluator works on *terms only* (it never looks at the AST or at the
interpreter), so it can be used to cross-check the interpreter.
Result is either a final state or *undefined* (⊥).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .. import ast as A
from . import terms as T
from .builder import build_term

DEFAULT_MAX_STEPS = 100_000

RULES = {
    "AF_ID": "id(st) = st",
    "AF_AS": "AS_x(f_a)(st) = st∇[x ↦ f_a(st)]",
    "AF_SEQ": "(f_S1 · f_S2)(st) = f_S2(f_S1(st))",
    "AF_IF_T": "IF(f_b, f_S1, f_S2)(st) = f_S1(st), якщо f_b(st) = true",
    "AF_IF_F": "IF(f_b, f_S1, f_S2)(st) = f_S2(st), якщо f_b(st) = false",
    "AF_WH_T": "WH(f_b, f_S)(st) = WH(f_b, f_S)(f_S(st)), якщо f_b(st) = true   (одна ітерація AF_WH)",
    "AF_WH_F": "WH(f_b, f_S)(st) = st, якщо f_b(st) = false   (вихід з циклу, AF_WH)",
    "AF_AS-⊥": "AS_x(f_a)(st) = ⊥, якщо f_a(st) = ⊥",
    "AF_IF-⊥": "IF(f_b, f_S1, f_S2)(st) = ⊥, якщо f_b(st) = ⊥",
    "AF_WH-⊥": "WH(f_b, f_S)(st) = ⊥, якщо f_b(st) = ⊥",
}


class Undefined(Exception):
    def __init__(self, kind: str, reason: str):
        super().__init__(reason)
        self.kind, self.reason = kind, reason   # kind: error | diverges | limit


@dataclass
class RuleStep:
    index: int
    depth: int
    rule: str
    term: str
    before: dict[str, int]
    after: dict[str, int] | None = None     # None: ⊥ (rule application did not finish)
    detail: str = ""

    def to_dict(self) -> dict:
        return {"index": self.index, "depth": self.depth, "rule": self.rule,
                "formula": RULES[self.rule], "term": self.term,
                "before": dict(sorted(self.before.items())),
                "after": None if self.after is None else dict(sorted(self.after.items())),
                "detail": self.detail}


@dataclass
class EvalResult:
    status: str                              # "defined" | "undefined"
    state: dict[str, int] | None             # final state, None for ⊥
    kind: str | None = None                  # for undefined: error | diverges | limit
    reason: str | None = None
    steps: list[RuleStep] = field(default_factory=list)

    @property
    def defined(self) -> bool:
        return self.status == "defined"

    def to_dict(self, with_steps: bool = True) -> dict:
        d: dict[str, Any] = {"status": self.status,
             "state": None if self.state is None else dict(sorted(self.state.items())),
             "kind": self.kind, "reason": self.reason, "rule_applications": len(self.steps)}
        if with_steps:
            d["steps"] = [s.to_dict() for s in self.steps]
        return d


# ---------------------------------------------------------------- basic functions

def _apply(op: str, args: list) -> int | bool:
    if op == "uminus":
        return -args[0]
    if op == "neg":
        return not args[0]
    a, b = args
    if op == "add":
        return a + b
    if op == "sub":
        return a - b
    if op == "mult":
        return a * b
    if op in ("div", "mod"):
        if b == 0:
            raise Undefined("error", f"'{op}' by zero")
        return a // b if op == "div" else a % b
    table = {"eq": a == b, "ne": a != b, "ls": a < b, "le": a <= b, "gr": a > b, "ge": a >= b}
    if op in table:
        return table[op]
    raise ValueError(f"unknown operation {op!r}")


def eval_expr(t: T.Term, st: Mapping[str, int]) -> int | bool:
    if isinstance(t, T.Const):
        return t.value
    if isinstance(t, T.Var):
        if t.name not in st:
            raise Undefined("error", f"variable '{t.name}' is not defined in the state")
        return st[t.name]
    if isinstance(t, T.Apply):
        if t.op == "and":
            return eval_expr(t.args[0], st) and eval_expr(t.args[1], st)
        if t.op == "or":
            return eval_expr(t.args[0], st) or eval_expr(t.args[1], st)
        return _apply(t.op, [eval_expr(a, st) for a in t.args])
    raise TypeError(f"not an expression term: {t!r}")


def _shown(v: int | bool) -> str:
    return "true" if v is True else "false" if v is False else str(v)


def _applied(t: T.Term, st: Mapping[str, int]) -> str:
    """Term with the state applied to the leaves: ``gr(2, 0)`` (and/or are lazy)."""
    if isinstance(t, (T.Const, T.Var)):
        return _shown(eval_expr(t, st))
    assert isinstance(t, T.Apply)
    if t.op in ("and", "or"):
        first = eval_expr(t.args[0], st)
        decided = (not first) if t.op == "and" else bool(first)
        second = "…" if decided else _applied(t.args[1], st)
        return f"{t.op}({_applied(t.args[0], st)}, {second})"
    return f"{t.op}({', '.join(_applied(a, st) for a in t.args)})"


def _explain(t: T.Term, st: Mapping[str, int]) -> str:
    """Course style: ``S²(gr, Y⇒, 0)(st) = gr(2, 0) = true`` (Y⇒(st) = 2)."""
    value = eval_expr(t, st)
    if isinstance(t, (T.Const, T.Var)):
        return f"{T.format_term(t)}(st) = {_shown(value)}"
    return f"{T.format_term(t)}(st) = {_applied(t, st)} = {_shown(value)}"


# ---------------------------------------------------------------- evaluator

class _Evaluator:
    def __init__(self, max_steps: int, record: bool):
        self.max_steps = max_steps
        self.record = record
        self.steps: list[RuleStep] = []
        self.count = 0

    def _enter(self, depth: int, rule: str, t: T.Term, st: dict, detail: str = ""):
        self.count += 1
        if self.count > self.max_steps:
            raise Undefined("limit", f"no result within {self.max_steps} rule applications "
                                     f"(treated as ⊥; raise --max-steps)")
        step = RuleStep(len(self.steps), depth, rule, T.format_term(t), dict(st), None, detail)
        if self.record:
            self.steps.append(step)
        return step

    def apply(self, t: T.Term, st: dict, depth: int = 0) -> dict:
        if isinstance(t, T.Id):
            s = self._enter(depth, "AF_ID", t, st)
            s.after = dict(st)
            return st
        if isinstance(t, T.Assign):
            try:
                detail, value = _explain(t.expr, st), eval_expr(t.expr, st)
            except Undefined as u:
                self._enter(depth, "AF_AS-⊥", t, st, u.reason)
                raise
            s = self._enter(depth, "AF_AS", t, st, detail)
            new = dict(st)
            new[t.var] = value
            s.after = dict(new)
            return new
        if isinstance(t, T.Comp):
            s = self._enter(depth, "AF_SEQ", t, st)
            mid = self.apply(t.first, st, depth + 1)
            out = self.apply(t.second, mid, depth + 1)
            s.after = dict(out)
            return out
        if isinstance(t, T.If):
            try:
                value, detail = eval_expr(t.cond, st), _explain(t.cond, st)
            except Undefined as u:
                self._enter(depth, "AF_IF-⊥", t, st, u.reason)
                raise
            s = self._enter(depth, "AF_IF_T" if value else "AF_IF_F", t, st, detail)
            out = self.apply(t.then if value else t.orelse, st, depth + 1)
            s.after = dict(out)
            return out
        if isinstance(t, T.While):
            seen: set[tuple] = set()
            cur = st
            while True:
                try:
                    value, detail = eval_expr(t.cond, cur), _explain(t.cond, cur)
                except Undefined as u:
                    self._enter(depth, "AF_WH-⊥", t, cur, u.reason)
                    raise
                s = self._enter(depth, "AF_WH_T" if value else "AF_WH_F", t, cur, detail)
                if not value:
                    s.after = dict(cur)
                    return cur
                key = tuple(sorted(cur.items()))
                if key in seen:
                    raise Undefined("diverges", "the loop returns to an earlier state; "
                                                "WH(f_b, f_S)(st) = ⊥ (never terminates)")
                seen.add(key)
                cur = self.apply(t.body, cur, depth + 1)
                s.after = dict(cur)
        raise TypeError(f"not a program term: {t!r}")


def evaluate_term(term: "T.Term | A.Program | str", state: Mapping[str, int] | None = None, *,
                  max_steps: int = DEFAULT_MAX_STEPS, record: bool = True,
                  extensions: bool = False) -> EvalResult:
    """Apply ``term`` (or a program, built into a term first) to ``state``."""
    if not isinstance(term, T.Term):
        term = build_term(term, extensions)
    ev = _Evaluator(max_steps, record)
    try:
        final = ev.apply(term, dict(state or {}))
    except Undefined as u:
        return EvalResult("undefined", None, u.kind, u.reason, ev.steps)
    return EvalResult("defined", final, None, None, ev.steps)
