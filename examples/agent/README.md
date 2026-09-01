# Agent loop: what happens when a contract fails

This example runs Loom's `AgentLoop` over the Keras → NN-IR → OP-IR lowering
pipeline from [`examples/lowering`](../lowering), starting from a draft task
that a contract rejects. It is the failure path end to end: reject, report,
revise, accept.

```bash
python examples/agent/main.py
```

## The trust boundary

```text
  agent ──writes──> draft/lower_dense_task.py     <- the only file it owns
                              │
  trusted, never shown:       ▼
  lowering/main.py    LoweringPipeline: import-keras -> repeat(lower-dense)
                      Verifier([GraphSchemaContract(NN_IR)])
                      Verifier([GraphSchemaContract(OP_IR)])
                              │
        ContractException ────┘──> render_feedback() ──> next revision
```

`PipelineRunner` names `lower-dense` as the one editable task slot and gives
the agent its draft path. Everything else — the pipeline's orchestration, the
contracts, the reference lowering in `examples/lowering` — stays on the
trusted side. "Every contract passed" is therefore a verdict about the
result, not something the agent can arrange.

## The seeded failure

`seed_task.py` is copied over `draft/lower_dense_task.py` at the start of
every run, so the loop always begins from the same rejected state. Its AQL
rewrite is correct: every `Dense` becomes `MatMul → BiasAdd → Activation`,
with the kernel and bias re-typed as `Weight` and `Bias`. What it omits is
the graph-level stamp, so the lowered graph still declares itself NN-IR:

```text
attempt 1: contracts REJECTED the draft

  Contract verdicts:
    FAIL  valid-OP-IR  ({'errors': 1, 'issues': 1})
            [error] graph._type: expected 'OP-IR', got 'NN-IR'
```

This is the interesting shape of failure: the vertices, edges, and operand
indices all validate. Only the claim the graph makes about itself is wrong,
and the contract is what catches it.

## The revision

The agent receives that report and nothing else, edits its draft, and the
unchanged pipeline runs again:

```text
  agent revises -> stamp-graph-type: graph still declares 'NN-IR'; stamp it
                   as 'OP-IR' once lowering has fired

  +        if modified:
  +            g.pmap["_type"] = OP_IR.name  # repair: declare OP-IR
  +            OP_IR.style(g)
           return TaskResult(output=g, modified=modified)

attempt 2: contracts ACCEPTED the draft

  PASS  valid-NN-IR  (after import)
  PASS  valid-OP-IR  (after lower)

  lowered graph declares 'OP-IR': 2x Activation, 2x Bias, 2x BiasAdd,
  1x Input, 2x MatMul, 1x Output, 2x Weight

converged after 2 attempt(s), 1 revision(s).
```

## Agents

| `--agent` | Needs | What revises the draft |
|---|---|---|
| `scripted` (default) | nothing | A repair catalogue keyed on contract-failure text |
| `claude` | the `claude` CLI on PATH | `claude -p` headless, no API key |
| `taskgen` | provider credentials | Loom's `TaskGen` over `PydanticAIProvider` |

```bash
python examples/agent/main.py --agent claude
python examples/agent/main.py --agent taskgen --provider openai --model gpt-5.6-sol
```

`ScriptedAgent` is a deterministic stand-in for a model, not a repair tool:
it matches the contract's issue text against a small catalogue in
`agents.py` and applies the corresponding source edit. It exists so the
loop's mechanism — failure report in, revised draft out, contracts re-run —
is reproducible and testable without a model, a network, or credentials. It
can only fix failures its catalogue names; anything else raises rather than
guessing. The other two agents put a real model behind the same seam.

## Test

```bash
pytest examples/agent/test_agent_loop.py
```

The test pins the trajectory: the seed draft fails `valid-OP-IR` on the
graph type, the loop converges after exactly one revision, and the accepted
graph declares OP-IR with no `Dense` left.

## Files

| Path | Trust | What |
|---|---|---|
| `seed_task.py` | trusted | The starting draft, restored before every run |
| `draft/lower_dense_task.py` | agent-owned | The editable task slot (generated) |
| `agents.py` | trusted | Feedback rendering and the three agents |
| `main.py` | trusted | The loop, the CLI, and the trajectory report |
| `test_agent_loop.py` | trusted | Reject → revise → accept, asserted |
| `test_providers.py` | trusted | Credential smoke test for `--agent taskgen` |
