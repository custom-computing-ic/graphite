"""Run the agent loop against a draft task that a contract rejects.

The pipeline, its contracts, and the reference lowering are trusted and are
never shown to the agent. The agent owns exactly one file --
``draft/lower_dense_task.py`` -- which starts as a copy of ``seed_task.py``:
a correct rewrite that forgets to stamp the graph-level IR type. The
``valid-OP-IR`` contract rejects it, the failure report is handed to the
agent, and the loop repeats until every contract passes.

    python examples/agent/main.py                     # deterministic, offline
    python examples/agent/main.py --agent claude      # `claude -p` CLI
    python examples/agent/main.py --agent taskgen --provider openai --model gpt-5.6-sol
"""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOWERING = HERE.parent / "lowering"
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(LOWERING))
sys.path.insert(0, str(HERE))

from loom.agent import AgentLoop, PipelineRunner

from agents import ClaudeAgent, ScriptedAgent, TaskGenAgent

SEED = HERE / "seed_task.py"
DRAFT = HERE / "draft" / "lower_dense_task.py"


def load_lowering_example():
    """Import ``examples/lowering/main.py`` under an unambiguous module name."""
    spec = importlib.util.spec_from_file_location(
        "lowering_example_main", LOWERING / "main.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def reset_draft() -> Path:
    """Restore the draft to the seed so every run starts from the failure."""
    DRAFT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SEED, DRAFT)
    return DRAFT


def build_agent(kind: str, draft: Path, *, model: str | None, provider: str):
    if kind == "scripted":
        return ScriptedAgent(draft)
    if kind == "claude":
        return ClaudeAgent(draft, model=model or "claude-opus-5")
    if kind == "taskgen":
        if model is None:
            raise SystemExit("--agent taskgen requires --model")
        return TaskGenAgent(draft, provider=provider, model=model)
    raise SystemExit(f"unknown agent {kind!r}")


def run_loop(kind: str = "scripted", *, max_attempts: int = 4,
             model: str | None = None, provider: str = "claude"):
    """Run one loop from the seed state; return ``(agent, result, failure)``."""
    lowering = load_lowering_example()
    draft = reset_draft()
    agent = build_agent(kind, draft, model=model, provider=provider)
    runner = PipelineRunner(
        lowering.LoweringPipeline,
        editable_tasks={"lower-dense"},
        draft={"lower-dense": draft},
    )
    loop = AgentLoop(runner, max_attempts=max_attempts)
    try:
        return agent, loop.run(lowering.build_keras_model(), agent), None
    except RuntimeError as exhausted:
        return agent, None, exhausted


def report(agent, result, failure) -> int:
    for attempt in agent.attempts:
        print(f"\nattempt {attempt.number}: contracts REJECTED the draft\n")
        print("  " + attempt.feedback.replace("\n", "\n  "))
        print(f"\n  agent revises -> {attempt.action}\n")
        print("  " + attempt.diff.rstrip().replace("\n", "\n  "))

    if failure is not None:
        print(f"\nloop did not converge: {failure}")
        return 1

    final = len(agent.attempts) + 1
    print(f"\nattempt {final}: contracts ACCEPTED the draft\n")
    for stage, checks in result.metadata["contract_results"].items():
        for name, check in checks.items():
            print(f"  PASS  {name}  (after {stage})")

    graph = result.output
    kinds = Counter(graph.pmap[v].get("_type") for v in graph.vertices)
    print(f"\n  lowered graph declares {graph.pmap['_type']!r}: "
          + ", ".join(f"{n}x {k}" for k, n in sorted(kinds.items())))
    revisions = len(agent.attempts)
    print(f"\nconverged after {final} attempt(s), {revisions} revision(s).")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", default="scripted",
                        choices=["scripted", "claude", "taskgen"])
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--model", default=None)
    parser.add_argument("--provider", default="claude",
                        help="pydantic-ai provider, for --agent taskgen")
    args = parser.parse_args()

    print("Loom agent loop over the Graphite lowering pipeline")
    print("  trusted    keras-to-op-ir pipeline + valid-NN-IR / valid-OP-IR contracts")
    print(f"  editable   lower-dense -> {DRAFT.relative_to(HERE.parents[1])}")
    print(f"  agent      {args.agent}")

    sys.exit(report(*run_loop(args.agent, max_attempts=args.max_attempts,
                              model=args.model, provider=args.provider)))
