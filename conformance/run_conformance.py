#!/usr/bin/env python3
"""Implementation-independent SIPL conformance runner (CORE-06).

It never imports the implementation: it only calls a command line that follows the
`sipl-cli/1` JSON contract (docs/cli.md) and compares the JSON with the expectations in
conformance/cases/*.json.   Usage:

    python conformance/run_conformance.py                     # uses "python -m sipl"
    python conformance/run_conformance.py --cmd "sipl"        # any other implementation
"""
import argparse
import glob
import json
import os
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def strip_spans(x):
    if isinstance(x, dict):
        return {k: strip_spans(v) for k, v in x.items() if k not in ("span", "target_span")}
    if isinstance(x, list):
        return [strip_spans(v) for v in x]
    return x


def call(cmd, command, source, state=None, extra=()):
    """``extra`` is e.g. ["--ext"]; only the *course* grammar is required of an implementation."""
    args = [*cmd, command, "-", "--json", *extra]
    if state:
        args += ["--state", ",".join(f"{k}={v}" for k, v in state.items())]
    p = subprocess.run(args, input=source, text=True, capture_output=True, encoding="utf-8")
    return p.returncode, json.loads(p.stdout)


def check_case(cmd, case):
    """Returns a list of failure messages (empty = passed)."""
    fails = []
    src, exp = case["source"], case["expect"]
    ext = ["--ext"] if case.get("extensions") else []
    code, doc = call(cmd, "parse", src, extra=ext)
    if "syntax_error" in exp:
        e = exp["syntax_error"]
        d = (doc["diagnostics"] or [{}])[0]
        if code != 1:
            fails.append(f"parse: exit code {code}, expected 1")
        if d.get("code") != e["code"]:
            fails.append(f"parse: error code {d.get('code')}, expected {e['code']}")
        if "line" in e and (d.get("span") or {}).get("line") != e["line"]:
            fails.append(f"parse: error line {(d.get('span') or {}).get('line')}, expected {e['line']}")
        if "col" in e and (d.get("span") or {}).get("col") != e["col"]:
            fails.append(f"parse: error col {(d.get('span') or {}).get('col')}, expected {e['col']}")
        return fails
    if code != 0:
        return [f"parse: exit code {code}, program should be valid: {doc['diagnostics']}"]
    if "ast" in exp and strip_spans(doc["result"]["ast"]) != exp["ast"]:
        fails.append("parse: AST differs from expected")
    if "term" in exp:
        _, t = call(cmd, "term", src, extra=ext)
        if t["result"]["text"] != exp["term"]:
            fails.append(f"term: {t['result']['text']!r}, expected {exp['term']!r}")
    for run in exp.get("runs", []):
        code, r = call(cmd, "run", src, run.get("state"), extra=ext)
        res = r["result"]
        if "final_state" in run:
            if res["status"] != "terminated" or res["state"] != run["final_state"]:
                fails.append(f"run {run.get('state')}: got {res['status']} {res['state']}, "
                             f"expected {run['final_state']}")
        else:
            got = (r["diagnostics"] or [{}])[0].get("code")
            if got != run["error"] or code != 3:
                fails.append(f"run {run.get('state')}: error {got} (exit {code}), expected {run['error']}")
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cmd", default=f"{shlex.quote(sys.executable)} -m sipl")
    ap.add_argument("--cases", default=os.path.join(HERE, "cases"))
    a = ap.parse_args()
    cmd = shlex.split(a.cmd)
    failed = total = 0
    for path in sorted(glob.glob(os.path.join(a.cases, "*.json"))):
        with open(path, encoding="utf-8") as f:
            case = json.load(f)
        total += 1
        fails = check_case(cmd, case)
        print(("FAIL " if fails else "ok   ") + case["name"])
        for m in fails:
            print("     -", m)
        failed += bool(fails)
    print(f"\n{total - failed}/{total} conformance cases passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
