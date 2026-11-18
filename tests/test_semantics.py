import glob
import json
import os
import random

import pytest

from sipl import build_term as _build_term
from sipl import evaluate_term as _evaluate_term
from sipl import format_term
from sipl import run as _run
from sipl import semantics as S
from sipl.semantics import terms as T

from test_parser import gen_seq, parse


def build_term(p, **kw):                            # short snippets use the SIPL-ext dialect
    kw.setdefault("extensions", True)
    return _build_term(p, **kw)


def evaluate_term(p, state=None, **kw):
    kw.setdefault("extensions", True)
    return _evaluate_term(p, state, **kw)


def run(p, state=None, **kw):
    kw.setdefault("extensions", True)
    return _run(p, state, **kw)

ROOT = os.path.dirname(os.path.dirname(__file__))


def example(name, folder="valid"):
    with open(os.path.join(ROOT, "examples", folder, name + ".sipl"), encoding="utf-8") as f:
        return f.read()


GOLDEN = sorted(glob.glob(os.path.join(ROOT, "tests", "golden", "*.term")))


@pytest.mark.parametrize("path", GOLDEN, ids=os.path.basename)
def test_golden_terms(path):
    name = os.path.basename(path)[:-5]
    with open(path, encoding="utf-8") as f:
        expected = f.read().strip()
    if name.startswith("ext_"):                       # examples/ext/<name>.sipl, SIPL-ext dialect
        got = format_term(_build_term(example(name[4:], "ext"), extensions=True))
    else:                                             # examples/valid/<name>.sipl, course grammar
        got = format_term(_build_term(example(name)))
    assert got == expected


def test_golden_set_covers_all_operators():
    text = " ".join(open(p, encoding="utf-8").read() for p in GOLDEN)
    for token in ["id", "AS_", "IF(", "WH(", " · ", "⇒", "S²(", "S¹(", "uminus", "mod", "div", "neg", "and",
                  "or", "add", "mult", "sub", "ne,", "ge,", "ls,", "gr,", "eq,"]:
        assert token in text, token


def test_practicum_example_matches_the_book_exactly():
    """Practical work 2: the term of x**y printed in the practicum."""
    src = "begin R := 1; while Y > 0 do begin R := R * X; Y := Y - 1 end end"
    assert format_term(build_term(src)) == (
        "AS_R(1) · WH(S²(gr, Y⇒, 0), AS_R(S²(mult, R⇒, X⇒)) · AS_Y(S²(sub, Y⇒, 1)))")
    assert format_term(_build_term(src)) == format_term(build_term(src))   # also valid without --ext
    res = _evaluate_term(src, {"X": 5, "Y": 2})            # the book's test: x = 5, y = 2
    assert res.state == {"X": 5, "Y": 0, "R": 25}


def test_term_structure_hand_checked():
    t = build_term("X := 1; Y := X")
    assert t == T.Comp(T.Assign("X", T.Const(1)), T.Assign("Y", T.Var("X")))
    assert format_term(t) == "AS_X(1) · AS_Y(X⇒)"          # S1 · S2: S1 runs first (NS_Stm_Seq)
    assert format_term(t, ascii=True) == "AS_X(1) . AS_Y(X=>)"


def test_negative_numeral_is_a_constant_unary_minus_is_not():
    assert build_term("X := -1") == T.Assign("X", T.Const(-1))
    assert format_term(build_term("X := -Y")) == "AS_X(S¹(uminus, Y⇒))"


def test_course_unicode_or_and_not_are_accepted():
    assert format_term(build_term("if ¬ X = 1 ∨ Y > 2 then skip else skip")) == \
        "IF(S²(or, S¹(neg, S²(eq, X⇒, 1)), S²(gr, Y⇒, 2)), id, id)"


def test_if_without_else_uses_identity_and_block_is_transparent():
    assert build_term("if X > 0 then begin Y := 1 end") == \
        T.If(T.Apply("gr", (T.Var("X"), T.Const(0))), T.Assign("Y", T.Const(1)), T.Id())


def test_term_to_dict_json_and_spans():
    t = build_term("X := 1")
    json.dumps(t.to_dict())
    assert t.span is not None and t.span.line == 1


def test_build_accepts_ast_or_text():
    assert build_term(parse("skip")) == build_term("skip") == T.Id()


# ---------------------------------------------------------------- evaluation

def test_eval_power():
    res = _evaluate_term(example("power"), {"X": 3, "Y": 4})
    assert res.defined and res.state == {"X": 3, "Y": 0, "R": 81}
    assert res.reason is None


def test_eval_accepts_term_object_and_does_not_mutate_input():
    st = {"X": 1}
    res = evaluate_term(build_term("X := X + 1"), st)
    assert res.state == {"X": 2} and st == {"X": 1}


def test_rule_trace_for_conditional():
    res = evaluate_term("if X > 0 then Y := 1 else Y := 2", {"X": 5})
    assert [s.rule for s in res.steps] == ["AF_IF_T", "AF_AS"]
    assert res.steps[0].depth == 0 and res.steps[1].depth == 1
    assert res.steps[0].detail == "S²(gr, X⇒, 0)(st) = gr(5, 0) = true"
    assert res.steps[1].after == {"X": 5, "Y": 1}
    assert [s.rule for s in evaluate_term("if X > 0 then Y := 1 else Y := 2", {"X": 0}).steps][0] == "AF_IF_F"


def test_rule_trace_for_loop_unfolding():
    res = evaluate_term("while N > 0 do N := N - 1", {"N": 2})
    rules = [s.rule for s in res.steps]
    assert rules == ["AF_WH_T", "AF_AS", "AF_WH_T", "AF_AS", "AF_WH_F"]
    assert res.steps[-1].after == {"N": 0}
    assert all(s.rule in S.RULES for s in res.steps)


def test_comp_and_id_rules():
    res = evaluate_term("skip; X := 1", {})
    assert [s.rule for s in res.steps] == ["AF_SEQ", "AF_ID", "AF_AS"]


def test_explanation_substitutes_values():
    res = evaluate_term("X := X * 2", {"X": 21})
    assert res.steps[0].detail == "S²(mult, X⇒, 2)(st) = mult(21, 2) = 42"


@pytest.mark.parametrize("src,state,kind", [
    ("X := Y", {}, "error"),
    ("X := 1 div 0", {}, "error"),
    ("while true do skip", {}, "diverges"),
    ("while N >= 0 do N := N + 1", {"N": 0}, "limit"),
])
def test_undefined_results(src, state, kind):
    res = evaluate_term(src, state, max_steps=1000)
    assert res.status == "undefined" and not res.defined
    assert res.state is None and res.kind == kind and res.reason
    json.dumps(res.to_dict())


def test_undefined_still_returns_partial_trace():
    res = evaluate_term("X := 1; Y := 1 div 0", {})
    assert res.steps[-1].rule == "AF_AS-⊥" and res.steps[-1].after is None
    assert "by zero" in res.steps[-1].detail
    assert res.steps[0].after is None                    # enclosing COMP did not finish


def test_result_to_dict_contains_formulas():
    d = evaluate_term("X := 1", {}).to_dict()
    assert d["steps"][0]["formula"] == S.RULES["AF_AS"]


def test_record_false_skips_trace():
    assert evaluate_term("X := 1", {}, record=False).steps == []


# ------------------------------------------- semantic term ≡ interpreter (cross-check)

CROSS = [("valid", "power", {"X": 2, "Y": 8}), ("valid", "gcd", {"A": 84, "B": 36}),
         ("ext", "collatz", {"N": 27}), ("valid", "multiplication", {"A": 6, "B": 7}),
         ("valid", "fibonacci", {"N": 20}), ("valid", "division", {"X": 99, "Y": 7}),
         ("valid", "conditions", {"X": 1, "Y": 1, "Z": 1}), ("ext", "ext_operators", {"X": 17, "Y": 5})]


@pytest.mark.parametrize("folder,name,state", CROSS)
def test_term_agrees_with_interpreter_on_examples(folder, name, state):
    a = run(example(name, folder), state)
    b = evaluate_term(example(name, folder), state)
    assert a.ok and b.defined and a.state == b.state


def test_term_agrees_with_interpreter_on_random_programs():
    """Invariant: both implementations give the same final state / the same ⊥ verdict."""
    r = random.Random(7)
    compared = 0
    for _ in range(400):
        src = gen_seq(r, 3)
        st = {"X": r.randint(-3, 5), "Y": r.randint(-3, 5), "Z": r.randint(-3, 5)}
        a = run(src, st, max_steps=3000)
        b = evaluate_term(src, st, max_steps=3000)
        if a.error and a.error.code == "RT-STEP-LIMIT" or b.kind == "limit":
            continue                                    # budgets are counted differently
        compared += 1
        if a.ok:
            assert b.defined and b.state == a.state, src
        elif a.error.code == "RT-INFINITE-LOOP":
            assert b.kind == "diverges", src
        else:
            assert b.status == "undefined" and b.kind == "error", src
    assert compared > 200
