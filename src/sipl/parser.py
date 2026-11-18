"""Recursive-descent parser producing the SIPL AST (see grammar/sipl.ebnf).

By default the parser accepts exactly the BNF of the course practicum.  With
``extensions=True`` it additionally accepts the documented SIPL-ext constructs.
"""

from __future__ import annotations

from . import ast as A
from .lexer import SiplSyntaxError, Token, tokenize
from .source import Diagnostic, SourceSpan

RELOPS = {"=", "<>", "!=", "<", "<=", ">", ">="}
STATEMENT_START = "an assignment, 'if', 'while', 'begin' or 'skip'"


class _Parser:
    def __init__(self, tokens: list[Token], extensions: bool = False):
        self.toks = tokens
        self.pos = 0
        self.ext = extensions

    def ext_error(self, tok: Token, what: str) -> SiplSyntaxError:
        return SiplSyntaxError(Diagnostic(
            "error", "SYN-EXTENSION",
            f"{what} is not part of the course BNF (it is an SIPL extension; enable it with --ext)",
            tok.span))

    # ---- helpers
    @property
    def tok(self) -> Token:
        return self.toks[self.pos]

    def advance(self) -> Token:
        t = self.toks[self.pos]
        if t.kind != "eof":
            self.pos += 1
        return t

    def is_(self, kind: str, text: str | None = None) -> bool:
        t = self.tok
        return t.kind == kind and (text is None or t.text == text)

    def accept(self, kind: str, text: str) -> Token | None:
        return self.advance() if self.is_(kind, text) else None

    def error(self, expected: str, code: str = "SYN-UNEXPECTED-TOKEN") -> SiplSyntaxError:
        t = self.tok
        return SiplSyntaxError(Diagnostic(
            "error", code, f"expected {expected}, found {t.describe()}", t.span))

    def expect(self, kind: str, text: str, what: str | None = None) -> Token:
        if self.is_(kind, text):
            return self.advance()
        raise self.error(what or f"'{text}'")

    # ---- statements
    def program(self) -> A.Program:
        if self.is_("eof"):
            raise SiplSyntaxError(Diagnostic(
                "error", "SYN-EMPTY-PROGRAM", "empty program: expected a statement", self.tok.span))
        if self.ext:
            body = self.sequence()
        else:                                   # course rule P1:  P ::= begin S end
            if not self.is_("kw", "begin"):
                raise self.error("'begin' (a program has the form: begin <statement> end)")
            body = self.statement()
        if not self.is_("eof"):
            if self.is_("kw", "end"):
                raise self.error("end of input ('end' without matching 'begin')",
                                 "SYN-UNBALANCED-END")
            raise self.error("end of input" if not self.ext else "';' or end of input")
        return A.Program(body, body.span)

    def sequence(self) -> A.Stmt:
        first = self.statement()
        items = [first]
        while self.accept("sym", ";"):
            items.append(self.statement())
        if len(items) == 1:
            return first
        return A.Seq(tuple(items), items[0].span.to(items[-1].span))

    def statement(self) -> A.Stmt:
        t = self.tok
        if t.kind == "kw":
            if t.text == "skip":
                self.advance()
                return A.Skip(t.span)
            if t.text == "begin":
                self.advance()
                body = self.sequence()
                end = self.expect("kw", "end", "'end' or ';'")
                return A.Block(body, t.span.to(end.span))
            if t.text == "if":
                self.advance()
                cond = self.cond()
                self.expect("kw", "then")
                then = self.statement()
                orelse = None
                last = then
                if self.ext:
                    has_else = self.accept("kw", "else") is not None
                else:                           # course rule S3: else is mandatory
                    self.expect("kw", "else")
                    has_else = True
                if has_else:
                    orelse = self.statement()
                    last = orelse
                return A.If(cond, then, orelse, t.span.to(last.span))
            if t.text == "while":
                self.advance()
                cond = self.cond()
                self.expect("kw", "do")
                body = self.statement()
                return A.While(cond, body, t.span.to(body.span))
        if t.kind == "ident":
            self.advance()
            self.expect("sym", ":=")
            value = self.arith()
            return A.Assign(t.text, value, t.span.to(value.span), t.span)
        raise self.error(STATEMENT_START)

    # ---- arithmetic
    def arith(self) -> A.Arith:
        left = self.term()
        while self.tok.kind == "sym" and self.tok.text in ("+", "-"):
            op = self.advance().text
            right = self.term()
            left = A.BinOp(op, left, right, left.span.to(right.span))
        return left

    def term(self) -> A.Arith:
        left = self.factor()
        while (self.tok.kind == "sym" and self.tok.text == "*") or \
              (self.tok.kind == "kw" and self.tok.text in ("div", "mod")):
            if self.tok.kind == "kw" and not self.ext:
                raise self.ext_error(self.tok, f"'{self.tok.text}'")
            op = self.advance().text
            right = self.factor()
            left = A.BinOp(op, left, right, left.span.to(right.span))
        return left

    def factor(self) -> A.Arith:
        t = self.tok
        if t.kind == "sym" and t.text == "-":
            nxt = self.toks[self.pos + 1]
            if nxt.kind == "number":            # negative numeral:  n ::= ... -1 | 0 | 1 ...
                self.advance()
                self.advance()
                return A.Num(-int(nxt.text), t.span.to(nxt.span))
            if not self.ext:
                raise self.ext_error(t, "unary minus before something other than a numeral")
            self.advance()
            operand = self.factor()
            return A.Neg(operand, t.span.to(operand.span))
        if t.kind == "number":
            self.advance()
            return A.Num(int(t.text), t.span)
        if t.kind == "ident":
            self.advance()
            return A.Var(t.text, t.span)
        if t.kind == "sym" and t.text == "(":
            self.advance()
            inner = self.arith()
            close = self.expect("sym", ")")
            # keep the parenthesised extent so spans cover the whole fragment
            return _rewrap(inner, t.span.to(close.span))
        raise self.error("an expression (number, variable, '-' or '(')",
                         "SYN-EXPECTED-EXPRESSION")

    # ---- conditions
    def cond(self) -> A.Cond:
        left = self.conj()
        while self.accept("kw", "or"):
            right = self.conj()
            left = A.BoolOp("or", left, right, left.span.to(right.span))
        return left

    def conj(self) -> A.Cond:
        left = self.negation()
        while self.is_("kw", "and"):
            if not self.ext:
                raise self.ext_error(self.tok, "'and'")
            self.advance()
            right = self.negation()
            left = A.BoolOp("and", left, right, left.span.to(right.span))
        return left

    def negation(self) -> A.Cond:
        t = self.tok
        if self.accept("kw", "not"):
            operand = self.negation()
            return A.Not(operand, t.span.to(operand.span))
        return self.atom()

    def atom(self) -> A.Cond:
        t = self.tok
        if t.kind == "kw" and t.text in ("true", "false"):
            if not self.ext:
                raise self.ext_error(t, f"'{t.text}'")
            self.advance()
            return A.BoolLit(t.text == "true", t.span)
        if t.kind == "sym" and t.text == "(":
            # "(a + b) > c" is a comparison; "(x > 1 and ...)" is a grouped condition.
            save = self.pos
            try:
                return self.comparison()
            except SiplSyntaxError as first:
                self.pos = save + 1
                try:
                    inner = self.cond()
                    close = self.expect("sym", ")")
                    return _rewrap(inner, t.span.to(close.span))
                except SiplSyntaxError as second:
                    raise _furthest(first, second)
        return self.comparison()

    def comparison(self) -> A.Cond:
        left = self.arith()
        t = self.tok
        if not (t.kind == "sym" and t.text in RELOPS):
            raise self.error("a comparison operator (=, <>, <, <=, >, >=)",
                             "SYN-EXPECTED-RELOP")
        if not self.ext and t.text not in ("=", ">"):
            raise self.ext_error(t, f"comparison '{t.text}' (the course has only = and >)")
        self.advance()
        right = self.arith()
        op = "<>" if t.text == "!=" else t.text
        return A.Compare(op, left, right, left.span.to(right.span))


def _rewrap(node, span: SourceSpan):
    """Return ``node`` with a widened span (parentheses included)."""
    import dataclasses
    return dataclasses.replace(node, span=span)


def _furthest(a: SiplSyntaxError, b: SiplSyntaxError) -> SiplSyntaxError:
    sa, sb = a.diagnostic.span, b.diagnostic.span
    pa, pb = (sa.start if sa else -1), (sb.start if sb else -1)
    if pa == pb:
        return a if a.diagnostic.code == "SYN-EXTENSION" else b
    return a if pa > pb else b


def parse(text: str, extensions: bool = False) -> A.Program:
    """Parse SIPL source. Raises :class:`SiplSyntaxError` with a structured diagnostic.

    ``extensions=False`` (default) accepts exactly the course BNF; ``True`` adds SIPL-ext.
    """
    return _Parser(tokenize(text), extensions).program()


def check(text: str, extensions: bool = False) -> list[Diagnostic]:
    """Return syntax diagnostics (empty list means the program is well-formed)."""
    try:
        parse(text, extensions)
    except SiplSyntaxError as e:
        return [e.diagnostic]
    return []
