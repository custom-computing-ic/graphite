# Graphite examples

These examples demonstrate Graphite and its Loom integrations:

1. defining and validating a typed IR;
2. matching and rewriting graphs with AQL;
3. importing a Keras model and lowering it from NN-IR to OP-IR;
4. running Loom's agent loop over a draft task that a contract rejects.

## Create the Conda environment

From the repository root, create the environment described by
[`environment.yml`](W:\cc\loom.git\examples\environment.yml):

```bash
conda env create -f examples/environment.yml
conda activate graphite-examples
```

The environment installs Python 3.12, Heterograph, TensorFlow, Graphite, and
Loom in editable mode. TensorFlow and Loom are needed only by the Keras
lowering and agent integration demos.

## Demo 1: NN-IR validation

Directory: `validation`

Run:

```bash
python examples/validation/main.py
```

This demo defines a small neural-network schema with typed vertices such as
`Input`, `Embedding`, `Dense`, `ReLU`, `SumPool`, and `Output`. It constructs a
graph through `NN_IR.new_graph()`, `new_vertex()`, and `new_edge()`, updates a
vertex, and prints the validation report.

The important idea is that the schema validates both metadata and structural
invariants. The example checks operation arity, acyclicity, and the expected
number of output vertices.

## Demo 2: GraphProcessor matching and rewriting

Directory: `processor_tests`

Run:

```bash
python examples/processor_tests/main.py
```

This is a lightweight executable test suite for `GraphProcessor`. It demonstrates:

- AQL chain and fan-in matching;
- semantic filtering with `where`;
- one-pass rewrites;
- creation of vertices and `finalize` metadata updates;
- disjoint-match enforcement;
- incoming, outgoing, and bidirectional rewiring;
- validation of invalid rewire annotations and finalize mutations.

The tests use plain `HGraph` objects so the matching and rewriting behavior is
easy to isolate from IR schema details. A successful run prints `PASS` for each
case and a final summary.

## Demo 3: Keras NN-IR to OP-IR lowering

Directory: `lowering`

Run from the repository root:

```bash
python examples/lowering/main.py
```

Or run the supplied Unix-style helper from the demo directory:

```bash
cd examples/lowering
bash run-main.sh
```

This demo builds a two-layer Keras model:

```text
Input → Dense(relu) → Dense(softmax) → Output
```

`ImportKerasTask` imports the model into NN-IR using the `GraphSchema` factory API.
`lower_dense_task.py` defines a `GraphProcessor`-backed `LowerDenseTask`. Each pass
matches a Dense node with its data input, weight, and bias, then rewrites it to:

```text
data → MatMul → BiasAdd → Activation
weight ────────┘
bias ───────────────┘
```

The Pipeline verifies the NN-IR contract after `ImportKerasTask`, repeats the
lowering Task until it reaches a fixed point, then verifies the OP-IR contract.

## Demo 4: Agent loop over a failing contract

Directory: `agent`

```bash
python examples/agent/main.py
```

This demo reuses the Demo 3 pipeline, but replaces its `lower-dense` task
with an editable draft that a contract rejects. `PipelineRunner` exposes
`lower-dense` as the only editable slot; the pipeline, the contracts, and the
reference lowering are never shown to the agent.

The draft's rewrite is correct but omits the graph-level type stamp, so the
lowered graph still declares itself NN-IR:

```text
FAIL  valid-OP-IR
        [error] graph._type: expected 'OP-IR', got 'NN-IR'
```

`AgentLoop` hands that report to the agent, the agent revises its draft, and
the unchanged pipeline runs again until every contract passes. The default
agent is deterministic and needs no model or credentials, so the loop is
reproducible; `--agent claude` and `--agent taskgen` put a real model behind
the same seam. `pytest examples/agent/test_agent_loop.py` asserts the
reject → revise → accept trajectory.

## General execution note

Run commands from the repository root so the editable Graphite installation and
example imports resolve consistently. Graph viewers may open an interactive
Heterograph WebView; close the viewer or interrupt the process after inspecting
the graph.
