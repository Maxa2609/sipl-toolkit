"""Lexer: source text -> tokens (with spans)."""

from __future__ import annotations

from dataclasses import dataclass

from .source import Diagnostic, LineIndex, SourceSpan

KEYWORDS = frozenset({
    "begin", "end", "if", "then", "else", "while", "do", "skip",
    "and", "or", "not", "true", "false", "div", "mod",
})

# Longest first so that ":=" / "<=" / "<>" win over ":" / "<".
SYMBOLS = (":=", "<=", ">=", "<>", "!=", ";", "+", "-", "*", "(", ")", "=", "<", ">")


@dataclass(frozen=True)
class Token:
    kind: str          # "ident" | "number" | "kw" | "sym" | "eof"
    text: str
    span: SourceSpan

    def describe(self) -> str:
        if self.kind == "eof":
            return "end of input"
        return f"'{self.text}'"


class SiplSyntaxError(Exception):
    """Raised by lexer/parser; carries a structured :class:`Diagnostic`."""

    def __init__(self, diagnostic: Diagnostic):
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


def tokenize(text: str) -> list[Token]:
    idx = LineIndex(text)
    tokens: list[Token] = []
    i, n = 0, len(text)

    def fail(code: str, msg: str, start: int, end: int) -> SiplSyntaxError:
        return SiplSyntaxError(Diagnostic("error", code, msg, idx.span(start, end)))

    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j == -1 else j + 1
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j == -1:
                raise fail("SYN-UNTERMINATED-COMMENT", "unterminated comment '/*'", i, i + 2)
            i = j + 2
        elif ch in "∨¬":          # course notation for 'or' / 'not'
            tokens.append(Token("kw", "or" if ch == "∨" else "not", idx.span(i, i + 1)))
            i += 1
        elif ch.isascii() and (ch.isalpha() or ch == "_"):
            j = i + 1
            while j < n and text[j].isascii() and (text[j].isalnum() or text[j] == "_"):
                j += 1
            word = text[i:j]
            kind = "kw" if word in KEYWORDS else "ident"
            tokens.append(Token(kind, word, idx.span(i, j)))
            i = j
        elif ch.isascii() and ch.isdigit():
            j = i + 1
            while j < n and text[j].isascii() and text[j].isdigit():
                j += 1
            if j < n and (text[j].isalpha() or text[j] == "_") and text[j].isascii():
                raise fail("SYN-BAD-NUMBER",
                           f"invalid number or identifier '{text[i:j + 1]}...'", i, j + 1)
            tokens.append(Token("number", text[i:j], idx.span(i, j)))
            i = j
        else:
            for sym in SYMBOLS:
                if text.startswith(sym, i):
                    tokens.append(Token("sym", sym, idx.span(i, i + len(sym))))
                    i += len(sym)
                    break
            else:
                raise fail("SYN-UNEXPECTED-CHAR", f"unexpected character {ch!r}", i, i + 1)
    tokens.append(Token("eof", "", idx.span(n, n)))
    return tokens
