"""SEM-01: build the semantic term recursively from the AST."""

from __future__ import annotations

from .. import ast as A
from ..parser import parse
from . import terms as T


OP_NAMES = {"+": "add", "-": "sub", "*": "mult", "div": "div", "mod": "mod",
            "=": "eq", "<>": "ne", "<": "ls", "<=": "le", ">": "gr", ">=": "ge",
            "and": "and", "or": "or"}


def build_expr(e: "A.Arith | A.Cond") -> T.Term:
    if isinstance(e, A.Num):
        return T.Const(e.value, e.span)
    if isinstance(e, A.BoolLit):
        return T.Const(e.value, e.span)
    if isinstance(e, A.Var):
        return T.Var(e.name, e.span)
    if isinstance(e, A.Neg):
        if isinstance(e.operand, A.Num):          # the course has negative numerals: n ::= ... -1 | 0 | 1 ...
            return T.Const(-e.operand.value, e.span)
        return T.Apply("uminus", (build_expr(e.operand),), e.span)
    if isinstance(e, (A.BinOp, A.Compare, A.BoolOp)):
        return T.Apply(OP_NAMES[e.op], (build_expr(e.left), build_expr(e.right)), e.span)
    if isinstance(e, A.Not):
        return T.Apply("neg", (build_expr(e.operand),), e.span)
    raise TypeError(f"unsupported expression node: {e!r}")


def build_stmt(s: A.Stmt) -> T.Term:
    if isinstance(s, A.Skip):
        return T.Id(s.span)
    if isinstance(s, A.Assign):
        return T.Assign(s.target, build_expr(s.value), s.span)
    if isinstance(s, A.Block):
        return build_stmt(s.body)
    if isinstance(s, A.Seq):
        term = build_stmt(s.statements[0])
        for nxt in s.statements[1:]:
            term = T.Comp(term, build_stmt(nxt), s.span)
        return term
    if isinstance(s, A.If):
        orelse = build_stmt(s.orelse) if s.orelse is not None else T.Id(None)
        return T.If(build_expr(s.cond), build_stmt(s.then), orelse, s.span)
    if isinstance(s, A.While):
        return T.While(build_expr(s.cond), build_stmt(s.body), s.span)
    raise TypeError(f"unsupported statement node: {s!r}")


def build_term(program: "A.Program | str", extensions: bool = False) -> T.Term:
    """Semantic term of a program (AST or source text)."""
    if isinstance(program, str):
        program = parse(program, extensions)
    return build_stmt(program.body)
