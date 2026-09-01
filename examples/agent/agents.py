"""Agents that revise the editable task from contract feedback.

All three implement Loom's ``Agent`` protocol (``initial_tasks`` /
``revise_tasks``) and differ only in how the next draft is produced:

``ScriptedAgent``
    Deterministic and offline. Repairs are selected by matching the text of
    the failing contract's issues against a small catalogue, then applied to
    the draft as a source edit. It needs no model, no network, and no
    credentials, so the loop's mechanism stays reproducible and testable.
    It is a stand-in for a model, not a general-purpose repair tool: it can
    only fix failures its catalogue names.

``ClaudeAgent``
    The same loop driven by a real model through the ``claude`` CLI in
    headless mode. No API key is required; it uses the local Claude Code
    login.

``TaskGenAgent``
    Loom's own :class:`~loom.agent.TaskGen` over a
    :class:`~loom.agent.PydanticAIProvider`, for the API-key path.

Every agent sees exactly one thing about the failure: the report rendered by
:func:`render_feedback`. The pipeline, the contracts, and the reference
solution stay on the trusted side of the boundary.
"""

from __future__ import annotations

import difflib
import importlib.util
import re
import shutil
import subprocess
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from uuid import uuid4

TASK_NAME = "lower-dense"
TASK_CLASS = "LowerDenseTask"


# --- what the agent is allowed to see ---------------------------------------

def render_feedback(failure: Exception) -> str:
    """Render one execution failure as the agent's only feedback channel.

    A ``ContractException`` is reported per contract, with the issues each
    one raised. Anything else is a task or runtime error and is reported as
    a traceback tail, so a draft that cannot even import produces feedback
    rather than a crash.
    """
    contract_results = getattr(failure, "contract_results", None)
    if not isinstance(contract_results, dict):
        tail = "".join(
            traceback.format_exception(type(failure), failure, failure.__traceback__)
        ).strip().splitlines()[-12:]
        return ("The draft task raised an exception before the contracts could "
                f"judge it.\n\n{type(failure).__name__}: {failure}\n\n"
                + "\n".join(tail))

    lines = ["Contract verdicts:"]
    for name, result in contract_results.items():
        if result.passed:
            lines.append(f"  PASS  {name}")
        else:
            lines.append(f"  FAIL  {name}  ({result.metrics})")
            for issue in result.failures:
                lines.append(f"          {issue}")
    return "\n".join(lines)


# --- loading a draft module as a Task factory -------------------------------

def task_factory(path: Path, class_name: str = TASK_CLASS) -> Callable:
    """Build a factory that loads the draft module fresh on every attempt."""
    def factory(pipeline):
        module_name = f"agent_draft_{path.stem}_{uuid4().hex}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load task module from {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, class_name)(pipeline)
    return factory


@dataclass
class Attempt:
    """One trip round the loop, as the agent observed it."""

    number: int
    feedback: str
    action: str
    diff: str = ""


class RecordingAgent:
    """Shared bookkeeping: hold the draft path and record every attempt."""

    def __init__(self, draft: Path):
        self.draft = Path(draft)
        self.attempts: list[Attempt] = []

    def initial_tasks(self, context):
        return {TASK_NAME: task_factory(self.draft)}

    def revise_tasks(self, context, *, failure: Exception):
        feedback = render_feedback(failure)
        before = self.draft.read_text(encoding="utf-8")
        action = self.revise(feedback, before)
        after = self.draft.read_text(encoding="utf-8")
        self.attempts.append(Attempt(
            number=len(self.attempts) + 1,
            feedback=feedback,
            action=action,
            diff="".join(difflib.unified_diff(
                before.splitlines(keepends=True), after.splitlines(keepends=True),
                fromfile=f"a/{self.draft.name}", tofile=f"b/{self.draft.name}",
            )),
        ))
        return {TASK_NAME: task_factory(self.draft)}

    def revise(self, feedback: str, source: str) -> str:
        """Rewrite the draft in place; return a one-line description."""
        raise NotImplementedError


# --- the deterministic agent ------------------------------------------------

@dataclass(frozen=True)
class Repair:
    """One source edit, keyed on the contract issue that motivates it."""

    name: str
    trigger: re.Pattern
    apply: Callable[[str, re.Match], str]
    describe: Callable[[re.Match], str]


def _stamp_graph_type(source: str, match: re.Match) -> str:
    """Stamp the graph-level ``_type`` once the rewrite has fired."""
    expected = match.group("expected")
    anchor = "        return TaskResult(output=g, modified=modified)"
    if anchor not in source:
        raise LookupError(f"cannot place the {expected!r} stamp: no return anchor")
    return source.replace(anchor, (
        "        if modified:\n"
        f"            g.pmap[\"_type\"] = OP_IR.name  # repair: declare {expected}\n"
        "            OP_IR.style(g)\n"
        + anchor
    ), 1)


REPAIRS: tuple[Repair, ...] = (
    Repair(
        name="stamp-graph-type",
        trigger=re.compile(
            r"graph\._type: expected '(?P<expected>[^']+)', got '(?P<actual>[^']+)'"
        ),
        apply=_stamp_graph_type,
        describe=lambda m: (
            f"graph still declares {m.group('actual')!r}; stamp it as "
            f"{m.group('expected')!r} once lowering has fired"
        ),
    ),
)


class ScriptedAgent(RecordingAgent):
    """Repair the draft from the contract report, without a model."""

    def revise(self, feedback: str, source: str) -> str:
        for repair in REPAIRS:
            match = repair.trigger.search(feedback)
            if match is None:
                continue
            self.draft.write_text(repair.apply(source, match), encoding="utf-8")
            return f"{repair.name}: {repair.describe(match)}"
        raise RuntimeError(
            "no repair in the catalogue matches this feedback; the scripted "
            "agent cannot revise the draft:\n" + feedback
        )


# --- the model-backed agents ------------------------------------------------

BRIEF = """\
You maintain one editable task module for a compiler built on the Loom
framework. The module defines a class named exactly `{cls}`, a `loom.core.Task`
subclass whose `execute(self, g)` lowers NN-IR `Dense` vertices into the OP-IR
chain MatMul -> BiasAdd -> Activation and returns
`TaskResult(output=g, modified=<bool>)`.

A trusted pipeline you cannot see runs your module inside `Pipeline.repeat()`
and then judges the result with human-written contracts. Those contracts have
just rejected the current draft.

Current draft module:
```python
{source}
```

Feedback from the contracts:
{feedback}

Return the complete corrected module in ONE ```python fence and nothing else.
"""


def _extract_module(text: str) -> str:
    fences = re.findall(r"```python\n(.*?)```", text, flags=re.DOTALL)
    return max(fences, key=len) if fences else text


class ClaudeAgent(RecordingAgent):
    """Revise the draft with the ``claude`` CLI in headless mode."""

    SYSTEM = ("You are a compiler engineer maintaining one bounded task module. "
              "Output only the requested Python module in a single ```python fence.")

    def __init__(self, draft: Path, *, model: str = "claude-opus-5", timeout: int = 1200):
        super().__init__(draft)
        self.model = model
        self.timeout = timeout

    def revise(self, feedback: str, source: str) -> str:
        if shutil.which("claude") is None:
            raise RuntimeError(
                "the `claude` CLI is not on PATH; install Claude Code or run "
                "this example with --agent scripted"
            )
        proc = subprocess.run(
            ["claude", "-p", "--model", self.model, "--output-format", "text",
             "--append-system-prompt", self.SYSTEM],
            input=BRIEF.format(cls=TASK_CLASS, source=source, feedback=feedback),
            capture_output=True, text=True, timeout=self.timeout,
        )
        if proc.returncode != 0:
            detail = (proc.stderr.strip() or proc.stdout.strip()
                      or "no output on stderr or stdout")
            raise RuntimeError(
                f"claude -p failed ({proc.returncode}): {detail[-2000:]}"
            )
        self.draft.write_text(_extract_module(proc.stdout), encoding="utf-8")
        return f"claude -p ({self.model}) rewrote the draft module"


class TaskGenAgent(RecordingAgent):
    """Revise the draft through Loom's own TaskGen/Provider seam."""

    def __init__(self, draft: Path, *, provider: str, model: str):
        super().__init__(draft)
        from loom.agent import PydanticAIProvider, TaskGen

        self._task_gen = TaskGen(
            provider=PydanticAIProvider(provider=provider, model=model),
            tasks={TASK_NAME},
        )
        self._label = f"TaskGen via {provider}:{model}"

    def revise_tasks(self, context, *, failure: Exception):
        feedback = render_feedback(failure)
        before = self.draft.read_text(encoding="utf-8")
        # TaskGen owns the prompt, the provider call, and the draft write.
        factories = self._task_gen.revise_tasks(context, failure=failure)
        after = self.draft.read_text(encoding="utf-8")
        self.attempts.append(Attempt(
            number=len(self.attempts) + 1,
            feedback=feedback,
            action=f"{self._label} rewrote the draft module",
            diff="".join(difflib.unified_diff(
                before.splitlines(keepends=True), after.splitlines(keepends=True),
                fromfile=f"a/{self.draft.name}", tofile=f"b/{self.draft.name}",
            )),
        ))
        return factories
