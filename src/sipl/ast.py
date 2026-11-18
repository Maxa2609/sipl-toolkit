"""Typed AST for SIPL. Nodes are immutable; ``span`` is ignored by equality."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Union

from .source import SourceSpan


class Node:
    """Base class: provides generic JSON export."""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": type(self).__name__}
        for f in dataclasses.fields(self):  # type: ignore[arg-type]
            out[f.name] = _export(getattr(self, f.name))
        return out


def _export(value: Any) -> Any:
    if isinstance(value, Node):
        return value.to_dict()
    if isinstance(value, SourceSpan):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_export(v) for v in value]
    return value


# ---------------------------------------------------------------- arithmetic

@dataclass(frozen=True)
class Num(Node):
    value: int
    span: SourceSpan = field(compare=False, repr=False)


@dataclass(frozen=True)
class Var(Node):
    name: str
    span: SourceSpan = field(compare=False, repr=False)


@dataclass(frozen=True)
class Neg(Node):
    operand: "Arith"
    span: SourceSpan = field(compare=False, repr=False)


@dataclass(frozen=True)
class BinOp(Node):
    op: str                       # + - * div mod
    left: "Arith"
    right: "Arith"
    span: SourceSpan = field(compare=False, repr=False)


Arith = Union[Num, Var, Neg, BinOp]


# ---------------------------------------------------------------- conditions

@dataclass(frozen=True)
class BoolLit(Node):
    value: bool
    span: SourceSpan = field(compare=False, repr=False)


@dataclass(frozen=True)
class Compare(Node):
    op: str                       # = <> < <= > >=   ("!=" is normalised to "<>")
    left: Arith
    right: Arith
    span: SourceSpan = field(compare=False, repr=False)


@dataclass(frozen=True)
class Not(Node):
    operand: "Cond"
    span: SourceSpan = field(compare=False, repr=False)


@dataclass(frozen=True)
class BoolOp(Node):
    op: str                       # and | or
    left: "Cond"
    right: "Cond"
    span: SourceSpan = field(compare=False, repr=False)


Cond = Union[BoolLit, Compare, Not, BoolOp]


# ---------------------------------------------------------------- statements

@dataclass(frozen=True)
class Skip(Node):
    span: SourceSpan = field(compare=False, repr=False)


@dataclass(frozen=True)
class Assign(Node):
    target: str
    value: Arith
    span: SourceSpan = field(compare=False, repr=False)
    target_span: SourceSpan = field(compare=False, repr=False, default=None)  # type: ignore[assignment]


@dataclass(frozen=True)
class Seq(Node):
    """``S1; S2; ...; Sn`` (n >= 2)."""
    statements: tuple["Stmt", ...]
    span: SourceSpan = field(compare=False, repr=False)


@dataclass(frozen=True)
class If(Node):
    cond: Cond
    then: "Stmt"
    orelse: "Stmt | None"
    span: SourceSpan = field(compare=False, repr=False)


@dataclass(frozen=True)
class While(Node):
    cond: Cond
    body: "Stmt"
    span: SourceSpan = field(compare=False, repr=False)


@dataclass(frozen=True)
class Block(Node):
    """``begin S end``."""
    body: "Stmt"
    span: SourceSpan = field(compare=False, repr=False)


Stmt = Union[Skip, Assign, Seq, If, While, Block]


@dataclass(frozen=True)
class Program(Node):
    body: Stmt
    span: SourceSpan = field(compare=False, repr=False)


# ---------------------------------------------------------------- unparsing

_ARITH_PREC = {"+": 1, "-": 1, "*": 2, "div": 2, "mod": 2}


def arith_to_str(e: Arith, parent: int = 0, right: bool = False) -> str:
    if isinstance(e, Num):
        return str(e.value)
    if isinstance(e, Var):
        return e.name
    if isinstance(e, Neg):
        if isinstance(e.operand, Num) and e.operand.value >= 0:
            return f"-({e.operand.value})"      # '-5' alone would read back as the numeral -5
        return "-" + arith_to_str(e.operand, 3)
    prec = _ARITH_PREC[e.op]
    s = (f"{arith_to_str(e.left, prec)} {e.op} "
         f"{arith_to_str(e.right, prec, True)}")
    return f"({s})" if prec < parent or (right and prec == parent) else s


def cond_to_str(c: Cond, parent: int = 0, right: bool = False) -> str:
    if isinstance(c, BoolLit):
        return "true" if c.value else "false"
    if isinstance(c, Compare):
        return f"{arith_to_str(c.left)} {c.op} {arith_to_str(c.right)}"
    if isinstance(c, Not):
        return "not " + cond_to_str(c.operand, 3)
    prec = 1 if c.op == "or" else 2
    s = (f"{cond_to_str(c.left, prec)} {c.op} "
         f"{cond_to_str(c.right, prec, True)}")
    return f"({s})" if prec < parent or (right and prec == parent) else s


def stmt_to_str(s: Stmt, indent: int = 0) -> str:
    """Canonical source text. ``parse(unparse(p)) == p`` holds for every program."""
    pad = "  " * indent
    if isinstance(s, Skip):
        return f"{pad}skip"
    if isinstance(s, Assign):
        return f"{pad}{s.target} := {arith_to_str(s.value)}"
    if isinstance(s, Seq):
        return (";\n").join(stmt_to_str(x, indent) for x in s.statements)
    if isinstance(s, Block):
        return f"{pad}begin\n{stmt_to_str(s.body, indent + 1)}\n{pad}end"
    if isinstance(s, If):
        out = f"{pad}if {cond_to_str(s.cond)} then\n{_branch(s.then, indent)}"
        if s.orelse is not None:
            out += f"\n{pad}else\n{_branch(s.orelse, indent)}"
        return out
    if isinstance(s, While):
        return f"{pad}while {cond_to_str(s.cond)} do\n{_branch(s.body, indent)}"
    raise TypeError(f"not a statement: {s!r}")


def _branch(s: Stmt, indent: int) -> str:
    # A Seq can only appear in a branch through a Block, so no wrapping needed.
    return stmt_to_str(s, indent + 1)


def unparse(p: Program) -> str:
    return stmt_to_str(p.body) + "\n"


def free_variables(node: Node) -> set[str]:
    """Names read anywhere in ``node``."""
    if isinstance(node, Var):
        return {node.name}
    out: set[str] = set()
    for f in dataclasses.fields(node):  # type: ignore[arg-type]
        v = getattr(node, f.name)
        if isinstance(v, Node):
            out |= free_variables(v)
        elif isinstance(v, tuple):
            for x in v:
                if isinstance(x, Node):
                    out |= free_variables(x)
    return out


def assigned_variables(node: Node) -> set[str]:
    if isinstance(node, Assign):
        return {node.target} | assigned_variables(node.value)
    out: set[str] = set()
    for f in dataclasses.fields(node):  # type: ignore[arg-type]
        v = getattr(node, f.name)
        if isinstance(v, Node):
            out |= assigned_variables(v)
        elif isinstance(v, tuple):
            for x in v:
                if isinstance(x, Node):
                    out |= assigned_variables(x)
    return out
