"""Execution events (CORE-04). Every event carries a snapshot of the state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..source import SourceSpan


@dataclass(frozen=True, kw_only=True)
class Event:
    seq: int                       # 0-based order of the event in the run
    step: int                      # number of statements started so far
    state: dict[str, int]          # snapshot AFTER the event took place
    span: SourceSpan | None = None
    type: str = field(init=False, default="Event")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type, "seq": self.seq, "step": self.step}
        for k, v in self.__dict__.items():
            if k in ("seq", "step", "type"):
                continue
            d[k] = v.to_dict() if isinstance(v, SourceSpan) else v
        return d


@dataclass(frozen=True, kw_only=True)
class BeforeStatement(Event):
    stmt: str = ""                 # AST node name: Assign | Skip | If | While
    text: str = ""                 # one-line source text of the statement head
    type: str = field(init=False, default="BeforeStatement")


@dataclass(frozen=True, kw_only=True)
class AfterStatement(Event):
    stmt: str = ""
    type: str = field(init=False, default="AfterStatement")


@dataclass(frozen=True, kw_only=True)
class VariableChanged(Event):
    name: str = ""
    old: int | None = None         # None: variable was not defined before
    new: int = 0
    type: str = field(init=False, default="VariableChanged")


@dataclass(frozen=True, kw_only=True)
class ConditionEvaluated(Event):
    context: str = ""              # "if" | "while"
    text: str = ""
    value: bool = False
    type: str = field(init=False, default="ConditionEvaluated")


@dataclass(frozen=True, kw_only=True)
class Finished(Event):
    status: str = ""               # "terminated" | "error"
    error: dict[str, Any] | None = None
    type: str = field(init=False, default="Finished")
