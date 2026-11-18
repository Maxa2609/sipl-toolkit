import glob
import os
import random
import re

import pytest

from sipl import ast as A
from sipl import check as _check
from sipl import parse as _parse
from sipl.lexer import KEYWORDS, SYMBOLS, SiplSyntaxError


def parse(text):
    """Most tests use the SIPL-ext dialect for short snippets; strict tests call _parse directly."""
    return _parse(text, extensions=True)


def check(text):
    return _check(text, extensions=True)


ROOT = os.path.dirname(os.path.dirname(__file__))
VALID = sorted(glob.glob(os.path.join(ROOT, "examples", "valid", "*.sipl")))
INVALID = sorted(glob.glob(os.path.join(ROOT, "examples", "invalid", "*.sipl")))
EXT = sorted(glob.glob(os.path.join(ROOT, "examples", "ext", "*.sipl")))


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_enough_examples():            # CORE-01 criterion: >=10 positive, >=10 negative
    assert len(VALID) >= 10 and len(INVALID) >= 10 and len(EXT) >= 3


# ---------------------------------------------------------------- course BNF is the default grammar

def test_course_grammar_requires_begin_end_around_the_program():
    assert _check("begin X := 1 end") == []
    d = _check("X := 1")[0]
    assert d.code == "SYN-UNEXPECTED-TOKEN" and "begin" in d.message
    assert _check("begin X := 1 end; Y := 2")             # nothing may follow the final 'end'


def test_course_grammar_requires_else():
    d = _check("begin if X > 0 then skip end")[0]
    assert d.code == "SYN-UNEXPECTED-TOKEN" and "'else'" in d.message
    assert _check("begin if X > 0 then skip else skip end") == []


@pytest.mark.parametrize("src,col", [
    ("begin X := Y div 2 end", 14), ("begin X := Y mod 2 end", 14),
    ("begin X := -Y end", 12), ("begin if X < 1 then skip else skip end", 12),
    ("begin if X >= 1 then skip else skip end", 12), ("begin if X <> 1 then skip else skip end", 12),
    ("begin if X > 1 and Y > 1 then skip else skip end", 16),
    ("begin while true do skip end", 13), ("begin while false do skip end", 13),
])
def test_every_extension_is_rejected_with_its_own_code_and_position(src, col):
    d = _check(src)[0]
    assert d.code == "SYN-EXTENSION" and "--ext" in d.message
    assert (d.span.line, d.span.col) == (1, col)
    assert _check(src, extensions=True) == []          # ...and accepted as an extension


def test_course_notation_and_numerals_are_accepted():
    assert _check("begin if ¬ X = 1 ∨ Y > -2 then X := (X + 1) * 2 - 3 else skip end") == []
    n = _parse("begin X := -5 end").body.body.value
    assert n == A.Num(-5, None)                         # n ::= ... -1 | 0 | 1 ...
    assert _parse("begin X := Y - 1 end").body.body.value.op == "-"      # binary minus is not a numeral


def test_negative_numeral_and_unary_minus_roundtrip():
    for src in ["X := -5", "X := -(5)", "X := - -5", "X := 3 - -5", "X := -5 * 2", "X := -(Y + 1)"]:
        prog = parse(src)
        assert parse(A.unparse(prog)) == prog, src



@pytest.mark.parametrize("path", VALID, ids=os.path.basename)
def test_valid_examples_are_in_the_course_language_and_roundtrip(path):
    prog = _parse(read(path))                      # default = exactly the course BNF
    assert _check(read(path)) == []
    assert isinstance(prog.body, A.Block)           # rule P1: begin S end
    assert _parse(A.unparse(prog)) == prog          # unparse is a right inverse of parse
    assert A.unparse(_parse(A.unparse(prog))) == A.unparse(prog)   # idempotent


@pytest.mark.parametrize("path", EXT, ids=os.path.basename)
def test_extension_examples_need_the_ext_flag(path):
    text = read(path)
    prog = _parse(text, extensions=True)
    assert _parse(A.unparse(prog), extensions=True) == prog
    assert _check(text)                             # rejected by the course grammar


@pytest.mark.parametrize("path", INVALID, ids=os.path.basename)
def test_invalid_examples_report_expected_code_with_position(path):
    text = read(path)
    expected = re.match(r"// error: (\S+)", text).group(1)
    diags = _check(text)
    assert len(diags) == 1
    d = diags[0]
    assert d.severity == "error" and d.code == expected
    assert d.span is not None and d.span.line >= 1 and d.span.col >= 1
    with pytest.raises(SiplSyntaxError):
        _parse(text)


def test_ast_shape_and_spans():
    src = "begin\n  R := 1;\n  while Y > 0 do Y := Y - 1\nend"
    prog = parse(src)
    block = prog.body
    assert isinstance(block, A.Block) and isinstance(block.body, A.Seq)
    asg, loop = block.body.statements
    assert asg == A.Assign("R", A.Num(1, None), None)       # spans ignored by ==
    assert (asg.span.line, asg.span.col) == (2, 3)
    assert src[asg.span.start:asg.span.end] == "R := 1"
    assert asg.target_span.end - asg.target_span.start == 1
    assert isinstance(loop, A.While)
    assert src[loop.span.start:loop.span.end] == "while Y > 0 do Y := Y - 1"
    assert src[loop.cond.span.start:loop.cond.span.end] == "Y > 0"
    assert (loop.span.line, loop.span.end_line) == (3, 3)
    assert src[prog.span.start:prog.span.end] == src


def test_nodes_are_own_types_not_library_trees():
    prog = parse("X := 1")
    assert type(prog).__module__ == "sipl.ast"
    assert isinstance(prog.body, A.Node)


def test_arithmetic_precedence_and_associativity():
    e = parse("X := 1 - 2 - 3 * 4 mod 5").body.value
    assert e == A.BinOp("-", A.BinOp("-", A.Num(1, None), A.Num(2, None), None),
                        A.BinOp("mod", A.BinOp("*", A.Num(3, None), A.Num(4, None), None),
                                A.Num(5, None), None), None)


def test_unary_minus_and_parentheses():
    e = parse("X := -(1 + 2) * 3").body.value
    assert isinstance(e, A.BinOp) and e.op == "*" and isinstance(e.left, A.Neg)
    assert A.arith_to_str(parse("X := 1 - (2 - 3)").body.value) == "1 - (2 - 3)"
    assert A.arith_to_str(parse("X := (1 - 2) - 3").body.value) == "1 - 2 - 3"


def test_condition_precedence():
    c = parse("if A < 1 or B < 2 and not C < 3 then skip").body.cond
    assert c.op == "or" and c.right.op == "and" and isinstance(c.right.right, A.Not)


def test_parenthesised_comparison_vs_grouped_condition():
    assert isinstance(parse("while (X + 1) > 2 do skip").body.cond, A.Compare)
    assert isinstance(parse("while (X > 2) do skip").body.cond, A.Compare)
    assert isinstance(parse("while (X > 2 or Y > 1) and Z = 0 do skip").body.cond, A.BoolOp)


def test_not_equal_alias_is_normalised():
    assert parse("if X != 1 then skip").body.cond.op == "<>"


def test_dangling_else_binds_to_nearest_if():
    s = parse("if A = 1 then if B = 1 then X := 1 else X := 2").body
    assert s.orelse is None and s.then.orelse is not None


def test_comments_are_ignored():
    assert parse("// c\nX := 1 /* mid */ ; Y := 2 // end") == parse("X := 1; Y := 2")


def test_error_positions_are_precise():
    d = check("X := 1;\nY := ;")[0]
    assert (d.span.line, d.span.col) == (2, 6)
    assert "expected an expression" in d.message and "';'" in d.message
    d = check("if (x > ) then skip")[0]
    assert (d.span.line, d.span.col) == (1, 9)


def test_case_sensitive_keywords():
    assert check("BEGIN skip END")             # BEGIN is an identifier -> syntax error
    assert check("begin skip end") == []


def test_variables_may_contain_digits_and_underscores():
    assert parse("x_1 := y2 + _z").body.target == "x_1"


def test_free_and_assigned_variables():
    p = parse("A := B + 1; if C > 0 then D := A else skip")
    assert A.free_variables(p) == {"A", "B", "C"}
    assert A.assigned_variables(p) == {"A", "D"}


def test_ast_to_dict_is_json_serialisable():
    import json
    d = parse("X := 1; Y := X").to_dict()
    json.dumps(d)
    assert d["kind"] == "Program" and d["body"]["kind"] == "Seq"


def test_grammar_file_matches_lexer():
    """grammar/sipl.ebnf must mention exactly the keywords and symbols of the lexer."""
    g = read(os.path.join(ROOT, "grammar", "sipl.ebnf"))
    terminals = set(re.findall(r'"([^"\s]+)"', g))
    for kw in KEYWORDS:
        assert kw in terminals, kw
    for sym in SYMBOLS:
        assert sym in terminals, sym


# ---- randomised round-trip over generated programs

def gen_arith(r, d):
    if d == 0 or r.random() < 0.3:
        return r.choice(["X", "Y", "Z", str(r.randint(0, 9))])
    k = r.random()
    if k < 0.15:
        return f"-{gen_arith(r, d - 1)}"
    if k < 0.3:
        return f"({gen_arith(r, d - 1)})"
    return f"{gen_arith(r, d - 1)} {r.choice(['+', '-', '*', 'div', 'mod'])} {gen_arith(r, d - 1)}"


def gen_cond(r, d):
    if d == 0 or r.random() < 0.4:
        return f"{gen_arith(r, 1)} {r.choice(['=', '<>', '<', '<=', '>', '>='])} {gen_arith(r, 1)}"
    k = r.random()
    if k < 0.2:
        return f"not {gen_cond(r, d - 1)}"
    if k < 0.3:
        return r.choice(["true", "false"])
    if k < 0.45:
        return f"({gen_cond(r, d - 1)})"
    return f"{gen_cond(r, d - 1)} {r.choice(['and', 'or'])} {gen_cond(r, d - 1)}"


def gen_stmt(r, d):
    k = r.random()
    if d == 0 or k < 0.35:
        return r.choice(["skip", f"{r.choice('XYZ')} := {gen_arith(r, 2)}"])
    if k < 0.55:
        return f"if {gen_cond(r, 2)} then {gen_stmt(r, d - 1)} else {gen_stmt(r, d - 1)}"
    if k < 0.65:
        return f"if {gen_cond(r, 2)} then begin {gen_seq(r, d - 1)} end"
    if k < 0.8:
        return f"while {gen_cond(r, 2)} do {gen_stmt(r, d - 1)}"
    return f"begin {gen_seq(r, d - 1)} end"


def gen_seq(r, d):
    return "; ".join(gen_stmt(r, d) for _ in range(r.randint(1, 3)))


def test_random_programs_roundtrip():
    r = random.Random(2026)
    for _ in range(300):
        prog = parse(gen_seq(r, 3))
        assert parse(A.unparse(prog)) == prog
