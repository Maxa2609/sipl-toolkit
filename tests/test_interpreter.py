import json
import os

import pytest

from sipl import parse as _parse
from sipl import run as _run
from sipl import trace as _trace
from sipl.interpreter import (AfterStatement, BeforeStatement, ConditionEvaluated,
                              Finished, Interpreter, VariableChanged)

ROOT = os.path.dirname(os.path.dirname(__file__))


def example(name, folder="valid"):
    with open(os.path.join(ROOT, "examples", folder, name + ".sipl"), encoding="utf-8") as f:
        return f.read()


def parse(text):
    return _parse(text, extensions=True)


def run(program, state=None, **kw):                 # short snippets use the SIPL-ext dialect
    kw.setdefault("extensions", True)
    return _run(program, state, **kw)


def trace(program, state=None, **kw):
    kw.setdefault("extensions", True)
    return _trace(program, state, **kw)


CASES = [
    ("power", {"X": 2, "Y": 10}, {"R": 1024, "X": 2, "Y": 0}),
    ("power", {"X": 7, "Y": 0}, {"R": 1, "X": 7, "Y": 0}),
    ("factorial", {"N": 5}, {"F": 120, "N": 1}),
    ("gcd", {"A": 48, "B": 18}, {"A": 6, "B": 6}),
    ("sum_to_n", {"N": 100}, {"N": 100, "S": 5050, "I": 101}),
    ("max", {"X": 3, "Y": 9}, {"X": 3, "Y": 9, "M": 9}),
    ("max", {"X": 9, "Y": 3}, {"X": 9, "Y": 3, "M": 9}),
    ("abs", {"X": -4}, {"X": 4}),
    ("abs", {"X": 4}, {"X": 4}),
    ("swap", {"X": 1, "Y": 2}, {"X": 2, "Y": 1, "T": 1}),
    ("division", {"X": 17, "Y": 5}, {"X": 17, "Y": 5, "Q": 3, "R": 2}),
    ("fibonacci", {"N": 10}, {"N": 10, "A": 55, "B": 89, "I": 10, "T": 89, "F": 55}),
    ("conditions", {"X": 1, "Y": 2, "Z": 0}, {"X": 1, "Y": 2, "Z": 0, "R": 0}),
    ("conditions", {"X": 0, "Y": 0, "Z": 0}, {"X": 0, "Y": 0, "Z": 0, "R": -1}),
    ("multiplication", {"A": 3, "B": 4}, {"A": 3, "B": 4, "P": 12, "I": 3, "J": 4}),
    ("skip", {"X": 1}, {"X": 1}),
    ("loop_with_condition", {"X": 1}, {"X": 10}),
    ("nested_if", {"X": 5}, {"X": 5, "S": 1}),
    ("nested_if", {"X": 0}, {"X": 0, "S": 0}),
    ("nested_if", {"X": -3}, {"X": -3, "S": -1}),
]

EXT_CASES = [
    ("collatz", {"N": 6}, {"N": 1, "C": 8}),
    ("digit_sum", {"N": 2026}, {"N": 0, "S": 10}),
    ("is_prime", {"N": 97}, {"N": 97, "P": 1, "D": 10}),
    ("is_prime", {"N": 91}, {"N": 91, "P": 0, "D": 8}),
    ("gcd_mod", {"A": 48, "B": 18}, {"A": 6, "B": 0, "T": 0}),
    ("nested_loops", {"A": 3, "B": 4}, {"A": 3, "B": 4, "P": 12, "I": 3, "J": 4}),
]


@pytest.mark.parametrize("name,init,final", EXT_CASES)
def test_extension_examples(name, init, final):
    res = _run(example(name, "ext"), init, extensions=True)
    assert res.ok and res.state == final


@pytest.mark.parametrize("name,init,final", [
    ("isqrt", {"N": 50}, {"N": 50, "R": 7}), ("isqrt", {"N": 49}, {"N": 49, "R": 7}),
    ("divisible", {"X": 9, "Y": 3}, {"X": 9, "Y": 3, "T": 0, "P": 1}),
    ("divisible", {"X": 9, "Y": 5}, {"X": 9, "Y": 5, "T": -1, "P": 0}),
    ("ap_sum", {"N": 3}, {"N": 3, "S": 18, "T": 9, "I": 3}),
])
def test_defense_programs_are_in_the_course_language(name, init, final):
    res = _run(example(name, "defense"), init)          # strict parser
    assert res.ok and res.state == final


@pytest.mark.parametrize("name,init,final", CASES)
def test_examples(name, init, final):
    res = _run(example(name), init)                      # course grammar, no extensions
    assert res.status == "terminated" and res.error is None
    assert res.state == final
    assert init == init and res.state is not init          # initial mapping not mutated


def test_input_state_is_not_mutated():
    init = {"X": 2, "Y": 3}
    _run(example("power"), init)
    assert init == {"X": 2, "Y": 3}


def test_short_circuit_avoids_error():
    assert run("if Y <> 0 and X div Y > 1 then Z := 1 else Z := 2", {"X": 5, "Y": 0}).state["Z"] == 2
    assert run("if Y = 0 or X div Y > 1 then Z := 1 else Z := 2", {"X": 5, "Y": 0}).state["Z"] == 1


def test_floor_division_semantics():
    st = run("Q := X div Y; R := X mod Y", {"X": -7, "Y": 2}).state
    assert (st["Q"], st["R"]) == (-4, 1)


@pytest.mark.parametrize("src,state,code", [
    ("X := Y", {}, "RT-UNDEFINED-VAR"),
    ("X := 1 div 0", {}, "RT-DIV-ZERO"),
    ("X := 5 mod (Y - Y)", {"Y": 3}, "RT-DIV-ZERO"),
    ("while true do skip", {}, "RT-INFINITE-LOOP"),
    ("while X >= 0 do X := X + 1", {"X": 0}, "RT-STEP-LIMIT"),
])
def test_runtime_errors_are_diagnostics_with_spans(src, state, code):
    res = run(src, state, max_steps=500)
    assert res.status == "error" and not res.ok
    assert res.error.code == code and res.error.span is not None


def test_error_keeps_state_reached_before_failure():
    res = run("X := 1; Y := 1 div 0", {})
    assert res.state == {"X": 1}


def test_step_limit_counts_statements():
    assert run("X := 1; X := 2; X := 3", max_steps=3).ok
    assert run("X := 1; X := 2; X := 3", max_steps=2).error.code == "RT-STEP-LIMIT"


def test_loop_detection_can_be_disabled_and_limit_still_stops():
    res = run("while true do skip", max_steps=100, detect_loops=False)
    assert res.error.code == "RT-STEP-LIMIT"


def test_long_terminating_loop_is_not_flagged():
    assert run("while N > 0 do N := N - 1", {"N": 5000}).ok


# ---------------------------------------------------------------- events (CORE-04)

def test_trace_event_sequence_for_assignment():
    res = trace("X := 1 + 2", {"X": 0})
    kinds = [e.type for e in res.events]
    assert kinds == ["BeforeStatement", "VariableChanged", "AfterStatement", "Finished"]
    before, changed, after, fin = res.events
    assert isinstance(before, BeforeStatement) and before.text == "X := 1 + 2"
    assert before.state == {"X": 0}                       # before the effect
    assert isinstance(changed, VariableChanged)
    assert (changed.name, changed.old, changed.new) == ("X", 0, 3)
    assert changed.state == {"X": 3}
    assert isinstance(after, AfterStatement) and isinstance(fin, Finished)
    assert fin.status == "terminated" and fin.state == {"X": 3}
    assert [e.seq for e in res.events] == [0, 1, 2, 3]


def test_trace_new_variable_has_old_none():
    ev = [e for e in trace("Y := 5").events if isinstance(e, VariableChanged)][0]
    assert ev.old is None


def test_trace_condition_events_for_while():
    res = trace("while N > 0 do N := N - 1", {"N": 2})
    conds = [e for e in res.events if isinstance(e, ConditionEvaluated)]
    assert [c.value for c in conds] == [True, True, False]
    assert all(c.context == "while" and c.text == "N > 0" for c in conds)
    assert [e.new for e in res.events if isinstance(e, VariableChanged)] == [1, 0]


def test_trace_spans_point_into_source():
    src = "X := 1;\nY := 2"
    res = trace(src)
    spans = [(e.span.line, src[e.span.start:e.span.end]) for e in res.events
             if isinstance(e, BeforeStatement)]
    assert spans == [(1, "X := 1"), (2, "Y := 2")]


def test_trace_is_balanced_and_json_serialisable():
    res = trace(example("collatz", "ext"), {"N": 6})
    n_before = sum(isinstance(e, BeforeStatement) for e in res.events)
    n_after = sum(isinstance(e, AfterStatement) for e in res.events)
    assert n_before == n_after == res.steps
    json.dumps(res.to_dict(with_events=True))
    assert isinstance(res.events[-1], Finished)


def test_trace_on_error_ends_with_finished_error():
    res = trace("X := 1 div 0")
    fin = res.events[-1]
    assert isinstance(fin, Finished) and fin.status == "error"
    assert fin.error["code"] == "RT-DIV-ZERO"


def test_observer_streaming_api():
    seen = []
    Interpreter(parse("X := 1; Y := X"), observer=seen.append).run({})
    assert [e.type for e in seen].count("VariableChanged") == 2
