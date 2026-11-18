"""Integration tests: the CLI is run as a real subprocess (`python -m sipl`)."""

import json
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(__file__))
EX = os.path.join(ROOT, "examples")
ENV = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"), PYTHONIOENCODING="utf-8")


def sipl(*args, stdin=None):
    p = subprocess.run([sys.executable, "-m", "sipl", *args], input=stdin, text=True,
                       capture_output=True, env=ENV, encoding="utf-8", timeout=60)
    return p.returncode, p.stdout, p.stderr


def j(*args, **kw):
    code, out, err = sipl(*args, "--json", **kw)
    return code, json.loads(out), err


def test_run_text():
    code, out, _ = sipl("run", f"{EX}/valid/power.sipl", "-s", "X=2,Y=10")
    assert code == 0 and out.strip() == "{R=1024, X=2, Y=0}"


def test_run_json_schema_is_stable():
    code, doc, _ = j("run", f"{EX}/valid/factorial.sipl", "--state", "N=5")
    assert code == 0
    assert set(doc) == {"schema", "command", "file", "ok", "diagnostics", "result"}
    assert doc["schema"] == "sipl-cli/1" and doc["command"] == "run" and doc["ok"] is True
    assert set(doc["result"]) == {"status", "state", "steps", "error"}
    assert doc["result"]["state"]["F"] == 120


def test_parse_json_contains_ast_with_spans():
    code, doc, _ = j("parse", f"{EX}/valid/swap.sipl")
    assert code == 0
    ast = doc["result"]["ast"]
    assert ast["kind"] == "Program" and ast["body"]["kind"] == "Block"      # rule P1: begin S end
    assert ast["body"]["body"]["kind"] == "Seq"
    assert ast["body"]["body"]["statements"][0]["span"]["line"] == 3


def test_parse_text_tree():
    code, out, _ = sipl("parse", f"{EX}/valid/skip.sipl")
    assert code == 0 and out.splitlines()[0].startswith("Program") and "Skip" in out


def test_check_ok_lists_inputs():
    code, out, _ = sipl("check", f"{EX}/valid/gcd.sipl")
    assert code == 0 and "inputs: A, B" in out
    code, doc, _ = j("check", f"{EX}/valid/power.sipl")
    assert doc["result"]["inputs"] == ["X", "Y"] and "R" in doc["result"]["assigned"]


def test_syntax_error_exit_code_and_message():
    code, out, err = sipl("check", f"{EX}/invalid/missing_expr.sipl")
    assert code == 1 and out == ""
    assert "missing_expr.sipl:2:12: error[SYN-EXPECTED-EXPRESSION]" in err


def test_syntax_error_json():
    code, doc, _ = j("run", f"{EX}/invalid/extra_end.sipl")
    assert code == 1 and doc["ok"] is False and doc["result"] is None
    d = doc["diagnostics"][0]
    assert d["code"] == "SYN-UNBALANCED-END" and d["span"]["line"] == 2


def test_runtime_error_exit_code_and_diagnostic():
    code, doc, err = j("run", "-", "--ext", stdin="X := 1 div 0")
    assert code == 3 and doc["result"]["status"] == "error"
    assert doc["diagnostics"][0]["code"] == "RT-DIV-ZERO"
    code, _, err = sipl("run", "-", stdin="begin X := Y end")
    assert code == 3 and "RT-UNDEFINED-VAR" in err


def test_step_limit_option():
    prog = "begin while N > -1 do N := N + 1 end"
    code, doc, _ = j("run", "-", "--max-steps", "10", "-s", "N=0", stdin=prog)
    assert code == 3 and doc["diagnostics"][0]["code"] == "RT-STEP-LIMIT"


def test_infinite_loop_is_reported():
    code, doc, _ = j("run", "-", stdin="begin while 0 = 0 do skip end")
    assert code == 3 and doc["diagnostics"][0]["code"] == "RT-INFINITE-LOOP"


def test_trace_json_events():
    code, doc, _ = j("trace", f"{EX}/valid/abs.sipl", "-s", "X=-3")
    types = [e["type"] for e in doc["result"]["events"]]
    assert code == 0 and types[0] == "BeforeStatement" and types[-1] == "Finished"
    assert "ConditionEvaluated" in types and "VariableChanged" in types


def test_trace_text():
    code, out, _ = sipl("trace", f"{EX}/valid/abs.sipl", "-s", "X=-3")
    assert code == 0 and "X: -3 -> 3" in out and "Finished: terminated" in out


def test_term_and_eval_term():
    code, out, _ = sipl("term", f"{EX}/valid/max.sipl")
    assert code == 0 and out.strip() == "IF(S²(gr, X⇒, Y⇒), AS_M(X⇒), AS_M(Y⇒))"
    code, out, _ = sipl("term", f"{EX}/valid/swap.sipl", "--ascii")
    assert " . " in out and "⇒" not in out and "=>" in out
    code, doc, _ = j("eval-term", f"{EX}/valid/power.sipl", "-s", "X=2,Y=3")
    assert code == 0 and doc["result"]["state"] == {"R": 8, "X": 2, "Y": 0}
    assert doc["result"]["steps"][0]["rule"] == "AF_SEQ" and "AF_AS" in doc["result"]["rules"]


def test_eval_term_undefined_exit_code():
    code, out, err = sipl("eval-term", "-", stdin="begin while 0 = 0 do skip end")
    assert code == 3 and "⊥" in out and "diverges" in err


def test_usage_errors():
    code, _, err = sipl("run", "no/such/file.sipl")
    assert code == 2 and "cannot read" in err
    code, doc, _ = j("run", "no/such/file.sipl")
    assert code == 2 and doc["diagnostics"][0]["code"] == "CLI-USAGE"
    code, _, err = sipl("run", "-", "-s", "X=abc", stdin="begin skip end")
    assert code == 2 and "NAME=INTEGER" in err
    assert sipl()[0] == 2 and sipl("bogus")[0] == 2


def test_version():
    code, out, _ = sipl("--version")
    assert code == 0 and out.startswith("sipl ")


def test_stdin_input():
    code, out, _ = sipl("run", "-", stdin="begin X := 2 * 21 end")
    assert code == 0 and out.strip() == "{X=42}"


def test_course_grammar_is_the_default_and_ext_enables_extensions():
    code, _, err = sipl("check", f"{EX}/ext/collatz.sipl")
    assert code == 1 and "SYN-UNEXPECTED-TOKEN" in err and "begin" in err
    assert sipl("check", f"{EX}/ext/collatz.sipl", "--ext")[0] == 0
    code, doc, _ = j("check", "-", stdin="begin X := Y div 2 end")
    assert code == 1 and doc["diagnostics"][0]["code"] == "SYN-EXTENSION"
    assert "--ext" in doc["diagnostics"][0]["message"]
    code, out, _ = sipl("run", f"{EX}/ext/collatz.sipl", "--ext", "-s", "N=6")
    assert code == 0 and "C=8" in out
    code, out, _ = sipl("term", f"{EX}/ext/ext_operators.sipl", "--ext")
    assert code == 0 and "S²(div, X⇒, Y⇒)" in out


def test_unicode_output_and_input_survive_a_legacy_windows_code_page():
    """Regression: on Windows piped output defaults to cp1251, which cannot encode '⇒' or '·'."""
    env = dict(ENV, PYTHONIOENCODING="cp1251", PYTHONUTF8="0")
    prog = "begin if X > 0 \u2228 \u00ac (Y = 0) then X := 1 else skip end"
    for args in (["term", "-"], ["term", "-", "--json"], ["eval-term", "-", "-s", "X=1,Y=0"]):
        p = subprocess.run([sys.executable, "-m", "sipl", *args], input=prog.encode("utf-8"),
                           capture_output=True, env=env, timeout=60)
        assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
        if "--json" in args:
            assert json.loads(p.stdout.decode("ascii"))["result"]["text"].startswith("IF(")
        else:
            assert "⇒".encode("utf-8") in p.stdout or b"=>" in p.stdout


def test_file_saved_with_utf8_bom_by_windows_editors_is_accepted(tmp_path):
    f = tmp_path / "bom.sipl"
    f.write_bytes(b"\xef\xbb\xbf" + "begin X := 1 end".encode("utf-8"))
    code, out, _ = sipl("run", str(f))
    assert code == 0 and out.strip() == "{X=1}"
