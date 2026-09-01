"""Check the loop's failure path: reject, revise, accept.

Runs the deterministic agent only, so the test needs no model, no network,
and no credentials.

    pytest examples/agent/test_agent_loop.py
    python examples/agent/test_agent_loop.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import DRAFT, SEED, load_lowering_example, reset_draft, run_loop


def test_seed_draft_is_rejected_by_the_op_ir_contract():
    """The starting draft lowers correctly but fails the target contract."""
    from agents import render_feedback, task_factory
    from graphite import ContractException
    from loom.agent import PipelineRunner

    lowering = load_lowering_example()
    draft = reset_draft()
    runner = PipelineRunner(lowering.LoweringPipeline,
                            editable_tasks={"lower-dense"},
                            draft={"lower-dense": draft})
    try:
        runner.run(lowering.build_keras_model(),
                   {"lower-dense": task_factory(draft)})
    except ContractException as failure:
        assert set(failure.failures) == {"valid-OP-IR"}
        assert "graph._type: expected 'OP-IR', got 'NN-IR'" in render_feedback(failure)
        assert failure.result.output.pmap["_type"] == "NN-IR"
    else:
        raise AssertionError("the seed draft was expected to fail valid-OP-IR")


def test_loop_converges_after_one_revision():
    """One contract failure, one repair, then every contract passes."""
    agent, result, failure = run_loop("scripted", max_attempts=4)

    assert failure is None, failure
    assert len(agent.attempts) == 1, "expected exactly one revision"

    revision = agent.attempts[0]
    assert "valid-OP-IR" in revision.feedback
    assert revision.action.startswith("stamp-graph-type")
    assert '+            g.pmap["_type"] = OP_IR.name' in revision.diff

    graph = result.output
    assert graph.pmap["_type"] == "OP-IR"
    assert not any(graph.pmap[v].get("_type") == "Dense" for v in graph.vertices)

    passed = {name: check.passed
              for checks in result.metadata["contract_results"].values()
              for name, check in checks.items()}
    assert passed == {"valid-NN-IR": True, "valid-OP-IR": True}


def test_every_run_starts_from_the_seed():
    """The draft is restored, so the failure path is never skipped."""
    reset_draft()
    assert DRAFT.read_text() == SEED.read_text()
    assert 'g.pmap["_type"] = OP_IR.name' not in DRAFT.read_text()


if __name__ == "__main__":
    for name, test in sorted(globals().items()):
        if name.startswith("test_") and callable(test):
            test()
            print(f"{name}: OK")
