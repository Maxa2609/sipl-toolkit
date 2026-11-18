"""Command line interface: ``sipl parse|check|run|trace|term|eval-term``.

Exit codes: 0 success; 1 the program has syntax errors; 2 usage / I/O error;
3 the program is syntactically valid but execution failed or the term is undefined (⊥).
With ``--json`` stdout is always one JSON document (schema ``sipl-cli/1``), see docs/cli.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Sequence

from . import __version__
from . import ast as A
from .analysis import input_variables
from .interpreter import (DEFAULT_MAX_STEPS, AfterStatement, BeforeStatement, ConditionEvaluated,
                          Finished, VariableChanged, run, trace)
from .parser import SiplSyntaxError, parse
from .semantics import RULES, build_term, evaluate_term, format_term
from .source import Diagnostic

SCHEMA = "sipl-cli/1"
EXIT_OK, EXIT_SYNTAX, EXIT_USAGE, EXIT_RUNTIME = 0, 1, 2, 3


class UsageError(Exception):
    pass


def _read_source(path: str) -> str:
    try:
        if path == "-":                      # always UTF-8, whatever the console code page is
            return sys.stdin.buffer.read().decode("utf-8-sig")
        with open(path, encoding="utf-8-sig") as f:      # tolerate the BOM added by Notepad
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise UsageError(f"cannot read '{path}': {e}") from None


def _parse_state(items: list[str] | None) -> dict[str, int]:
    state: dict[str, int] = {}
    for item in items or []:
        for part in item.split(","):
            part = part.strip()
            if not part:
                continue
            name, eq, value = part.partition("=")
            try:
                if not eq or not name.strip().isidentifier():
                    raise ValueError
                state[name.strip()] = int(value)
            except ValueError:
                raise UsageError(f"bad --state entry {part!r}; expected NAME=INTEGER") from None
    return state


def _envelope(command: str, file: str, ok: bool, diagnostics: list[Diagnostic],
              result: Any = None) -> dict[str, Any]:
    return {"schema": SCHEMA, "command": command, "file": file, "ok": ok,
            "diagnostics": [d.to_dict() for d in diagnostics], "result": result}


def _ast_text(node: Any, indent: int = 0) -> str:
    pad = "  " * indent
    if not isinstance(node, A.Node):
        return f"{pad}{node}"
    scalars = [f"{k}={v!r}" for k, v in node.__dict__.items()
               if not isinstance(v, (A.Node, tuple)) and k not in ("span", "target_span") and v is not None]
    span = getattr(node, "span", None)
    pos = f" @{span}" if span else ""
    lines = [f"{pad}{type(node).__name__}({', '.join(scalars)}){pos}"]
    for k, v in node.__dict__.items():
        if isinstance(v, A.Node):
            lines.append(_ast_text(v, indent + 1))
        elif isinstance(v, tuple):
            lines.extend(_ast_text(x, indent + 1) for x in v)
    return "\n".join(lines)


def _fmt_state(st: dict[str, int] | None) -> str:
    if st is None:
        return "⊥"
    return "{" + ", ".join(f"{k}={v}" for k, v in sorted(st.items())) + "}"


def execute(args: argparse.Namespace, out: list[str], err: list[str]) -> tuple[int, dict[str, Any]]:
    """Runs a command; returns (exit code, JSON envelope). Text goes to ``out``/``err``."""
    cmd, path = args.command, args.file
    text = _read_source(path)
    try:
        program = parse(text, args.ext)
    except SiplSyntaxError as e:
        err.append(e.diagnostic.format(path))
        return EXIT_SYNTAX, _envelope(cmd, path, False, [e.diagnostic])

    if cmd == "parse":
        out.append(_ast_text(program))
        return EXIT_OK, _envelope(cmd, path, True, [], {"ast": program.to_dict()})

    if cmd == "check":
        inputs = input_variables(program)
        out.append(f"{path}: OK (inputs: {', '.join(inputs) or 'none'})")
        return EXIT_OK, _envelope(cmd, path, True, [], {
            "inputs": inputs, "assigned": sorted(A.assigned_variables(program))})

    if cmd == "term":
        term = build_term(program)
        out.append(format_term(term, ascii=args.ascii))
        return EXIT_OK, _envelope(cmd, path, True, [], {
            "text": format_term(term), "ascii": format_term(term, ascii=True),
            "term": term.to_dict()})

    state = _parse_state(args.state)

    if cmd in ("run", "trace"):
        fn = run if cmd == "run" else trace
        res = fn(program, state, max_steps=args.max_steps)
        if cmd == "trace":
            for ev in res.events:
                at = f" @{ev.span}" if ev.span else ""
                if isinstance(ev, Finished):
                    out.append(f"#{ev.seq} Finished: {ev.status} {_fmt_state(ev.state)}")
                elif isinstance(ev, BeforeStatement):
                    out.append(f"#{ev.seq} Before {ev.text}{at}")
                elif isinstance(ev, AfterStatement):
                    out.append(f"#{ev.seq} After  {ev.stmt}{at}")
                elif isinstance(ev, VariableChanged):
                    out.append(f"#{ev.seq} {ev.name}: {ev.old} -> {ev.new}")
                elif isinstance(ev, ConditionEvaluated):
                    out.append(f"#{ev.seq} Condition {ev.text} = {str(ev.value).lower()}")
        else:
            out.append(_fmt_state(res.state))
        if res.error:
            err.append(res.error.format(path))
        diags = [res.error] if res.error else []
        return (EXIT_OK if res.ok else EXIT_RUNTIME), _envelope(
            cmd, path, res.ok, diags, res.to_dict(with_events=(cmd == "trace")))

    term = build_term(program)
    # eval-term
    ev_res = evaluate_term(term, state, max_steps=args.max_steps)
    out.append(f"{format_term(term, ascii=args.ascii)}")
    for s in ev_res.steps:
        mark = _fmt_state(s.after) if s.after is not None else "⊥"
        out.append(f"{'  ' * s.depth}[{s.rule}] {s.term}  {_fmt_state(s.before)} => {mark}"
                   + (f"   ({s.detail})" if s.detail else ""))
    if ev_res.defined:
        out.append(f"result: {_fmt_state(ev_res.state)}")
    else:
        out.append(f"result: ⊥ ({ev_res.kind}: {ev_res.reason})")
    if not ev_res.defined:
        err.append(f"{path}: term undefined on {_fmt_state(state)}: {ev_res.kind}: {ev_res.reason}")
    payload = ev_res.to_dict()
    payload["rules"] = RULES
    return (EXIT_OK if ev_res.defined else EXIT_RUNTIME), _envelope(cmd, path, ev_res.defined, [], payload)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sipl", description="SIPL Language Toolkit")
    p.add_argument("--version", action="version", version=f"sipl {__version__}")
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def common(sp: argparse.ArgumentParser, *, state=False, ascii_=False) -> None:
        sp.add_argument("file", help="SIPL source file, or '-' for stdin")
        sp.add_argument("--json", action="store_true", help="print one JSON document on stdout")
        sp.add_argument("--ext", action="store_true",
                        help="also accept SIPL-ext constructs (div, mod, <, and, if without else, ...); "
                             "default: exactly the course BNF")
        if state:
            sp.add_argument("-s", "--state", action="append", metavar="X=1,Y=2",
                            help="initial state (repeatable)")
            sp.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS,
                            help=f"execution budget (default {DEFAULT_MAX_STEPS})")
        if ascii_:
            sp.add_argument("--ascii", action="store_true", help="use 'o' instead of '∘'")

    common(sub.add_parser("parse", help="print the AST"))
    common(sub.add_parser("check", help="check syntax, list input variables"))
    common(sub.add_parser("run", help="execute a program"), state=True)
    common(sub.add_parser("trace", help="execute and print the event trace"), state=True)
    common(sub.add_parser("term", help="print the semantic term"), ascii_=True)
    common(sub.add_parser("eval-term", help="evaluate the semantic term with a rule trace"),
           state=True, ascii_=True)
    return p


def _use_utf8_when_piped() -> None:
    """Windows pipes default to a legacy code page (cp1251, cp1252, ...) that cannot hold ⇒ or ·."""
    for stream in (sys.stdout, sys.stderr):
        if not stream.isatty() and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    _use_utf8_when_piped()
    args = build_parser().parse_args(argv)
    out: list[str] = []
    err: list[str] = []
    try:
        code, envelope = execute(args, out, err)
    except UsageError as e:
        if args.json:
            print(json.dumps({"schema": SCHEMA, "command": args.command, "file": args.file,
                              "ok": False, "diagnostics": [
                                  Diagnostic("error", "CLI-USAGE", str(e)).to_dict()],
                              "result": None}))
        else:
            print(f"sipl: error: {e}", file=sys.stderr)
        return EXIT_USAGE
    if args.json:
        print(json.dumps(envelope, indent=2))      # ASCII-only JSON is valid in every encoding
    else:
        if out:
            print("\n".join(out))
        for line in err:
            print(line, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
