"""Semantic terms of SIPL programs, in the notation of the course practicum (practical work 2).

A program denotes a partial function on states (sem_P / sem_S / sem_A / sem_B)::

    skip                   ->  id                          (NS_Stm_skip)
    x := a                 ->  AS_x(sem_A(a))              (NS_Stm_As)
    S1; S2                 ->  sem_S(S1) · sem_S(S2)       (NS_Stm_Seq; S1 runs first)
    if b then S1 else S2   ->  IF(sem_B(b), sem_S(S1), sem_S(S2))
    while b do S           ->  WH(sem_B(b), sem_S(S))
    begin S end            ->  sem_S(S)
    n                      ->  n                           (NS_A_Num)
    x                      ->  x⇒                          (NS_A_Var)
    a1 + a2                ->  S²(add, sem_A(a1), sem_A(a2))   and so on for sub, mult, gr, eq, or, neg

Operations that the practicum does not define are extensions with these names:
div, mod, uminus, ne, ls, le, ge, and.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Union

from ..source import SourceSpan


class Term:
    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": type(self).__name__}
        for f in dataclasses.fields(self):  # type: ignore[arg-type]
            v = getattr(self, f.name)
            if isinstance(v, Term):
                v = v.to_dict()
            elif isinstance(v, tuple):
                v = [x.to_dict() if isinstance(x, Term) else x for x in v]
            elif isinstance(v, SourceSpan):
                v = v.to_dict()
            out[f.name] = v
        return out

    def __str__(self) -> str:
        return format_term(self)




@dataclass(frozen=True)
class Const(Term):
    value: Union[int, bool]
    span: SourceSpan | None = field(compare=False, repr=False, default=None)


@dataclass(frozen=True)
class Var(Term):
    name: str
    span: SourceSpan | None = field(compare=False, repr=False, default=None)


@dataclass(frozen=True)
class Apply(Term):
    """Application of a basic function/predicate: ``+ - * div mod neg = <> < <= > >= and or not``."""
    op: str
    args: tuple[Term, ...]
    span: SourceSpan | None = field(compare=False, repr=False, default=None)


@dataclass(frozen=True)
class Id(Term):
    span: SourceSpan | None = field(compare=False, repr=False, default=None)


@dataclass(frozen=True)
class Assign(Term):
    var: str
    expr: Term
    span: SourceSpan | None = field(compare=False, repr=False, default=None)


@dataclass(frozen=True)
class Comp(Term):
    """``second ∘ first``: run ``first``, then ``second``."""
    first: Term
    second: Term
    span: SourceSpan | None = field(compare=False, repr=False, default=None)


@dataclass(frozen=True)
class If(Term):
    cond: Term
    then: Term
    orelse: Term
    span: SourceSpan | None = field(compare=False, repr=False, default=None)


@dataclass(frozen=True)
class While(Term):
    cond: Term
    body: Term
    span: SourceSpan | None = field(compare=False, repr=False, default=None)


def _flatten(t: Term) -> list[Term]:
    """Execution-ordered parts of a composition chain."""
    if isinstance(t, Comp):
        return _flatten(t.first) + _flatten(t.second)
    return [t]


_SUP = {1: "¹", 2: "²", 3: "³"}


def format_term(t: Term, ascii: bool = False) -> str:
    """Course notation: ``AS_R(1) · WH(S²(gr, Y⇒, 0), ...)``.  ``ascii=True``: ``S2``, ``=>``, `` . ``."""
    def f(x: Term) -> str:
        return format_term(x, ascii)

    if isinstance(t, Const):
        if isinstance(t.value, bool):
            return "true" if t.value else "false"
        return str(t.value)
    if isinstance(t, Var):
        return t.name + ("=>" if ascii else "⇒")
    if isinstance(t, Apply):
        n = len(t.args)
        sup = str(n) if ascii else _SUP.get(n, str(n))
        return f"S{sup}({', '.join([t.op, *[f(a) for a in t.args]])})"
    if isinstance(t, Id):
        return "id"
    if isinstance(t, Assign):
        return f"AS_{t.var}({f(t.expr)})"
    if isinstance(t, Comp):
        return (" . " if ascii else " · ").join(f(p) for p in _flatten(t))
    if isinstance(t, If):
        return f"IF({f(t.cond)}, {f(t.then)}, {f(t.orelse)})"
    if isinstance(t, While):
        return f"WH({f(t.cond)}, {f(t.body)})"
    raise TypeError(f"not a term: {t!r}")
