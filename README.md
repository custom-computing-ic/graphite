# Graphite

Graphite is a Python toolkit for describing, validating, matching, and
rewriting Heterograph-based intermediate representations (IRs). It also
provides contracts for checking the output of a graph workflow. Graphite has no
Loom dependency; any object with an `output` attribute can be verified.

## Examples

The runnable examples are in [`examples/`](examples). `validation` and
`processor_tests` require Graphite only; `lowering` and `agent` are Graphite
and Loom integration examples.

To run the examples, it is highly recommended to install conda to install OS-dependent libraries such as `graph-tool`.

```bash
cd examples/
conda env create -f environment.yml
conda activate graphite-examples
```


## IR schemas

`GraphSchema` defines the accepted graph, vertex, and edge metadata with
Pydantic models. It constructs correctly typed graph elements and returns a
`ValidationReport` instead of failing at the first invalid element. Each graph
element uses `_type` to select its model.

```python
from typing import Literal

from pydantic import BaseModel, Field
from graphite import GraphSchema


class ConstantProps(BaseModel):
    type_: Literal["Constant"] = Field(alias="_type")
    value: float


class NegateProps(BaseModel):
    type_: Literal["Negate"] = Field(alias="_type")


class DataEdgeProps(BaseModel):
    type_: Literal["data"] = Field(alias="_type")


ir = GraphSchema(
    name="ArithmeticIR",
    vertex={"Constant": ConstantProps, "Negate": NegateProps},
    edge={"data": DataEdgeProps},
)

graph = ir.new_graph()
constant = ir.new_vertex(graph, "Constant", value=3.0)
negate = ir.new_vertex(graph, "Negate")
ir.new_edge(graph, constant, negate, "data")

report = ir.validate(graph)
assert report.ok
```

Pass `rules` to `GraphSchema` for structural validation such as arity,
acyclicity, or required inputs and outputs. A rule receives the `HGraph` and
returns a list of `Issue` values. `update_vertex()` and `update_edge()` apply
the same Pydantic validation when metadata changes.

## Graph processor

`GraphProcessor` finds AQL patterns and applies one in-place rewrite pass. A
result contains `matches`, the parsed `pattern`, and a `modified` flag.

See [GraphProcessor.md](GraphProcessor.md) for the AQL grammar, matching
semantics, rewrites, rewiring, and a complete Dense-lowering walkthrough.

```python
from heterograph import HGraph
from graphite import GraphProcessor

graph = HGraph()
graph.add_vx(3)
graph.add_edge(0, 1)
graph.add_edge(1, 2)

processor = GraphProcessor(snapshot=False)
result = processor.run(
    graph,
    select="a => b => c",
    rewrite="a => c",
)

assert result["modified"]
assert set(graph.edges) == {(0, 2)}
```

Use `where(graph, **match)` to filter matches and `finalize(graph, **match)`
to initialize created vertices or metadata. `finalize` must return a boolean.
Rewrites require disjoint matches; Graphite rejects overlapping matches before
mutating the graph. Rewire annotations preserve boundary connections when a
matched vertex is replaced:

```python
processor.run(
    graph,
    select="a => b => c",
    rewrite="a => x {rewire: b} => c",
)
```

`GraphProcessor(snapshot=True)` is the default and records graphs in a
Heterograph WebView. Use `snapshot=False` for scripts and tests without a
viewer.

## Contracts

`Contract` evaluates one object with an `output` attribute and returns a
`ContractResult`. `Verifier` runs a collection of contracts, retaining all
results; if any fail, it raises `ContractException` with the individual
failures.

`GraphSchemaContract` validates a result's graph output against a schema:

```python
from dataclasses import dataclass

from graphite import GraphSchemaContract, Verifier


@dataclass
class BuildResult:
    output: object


checks = Verifier([GraphSchemaContract(ir)])
contract_results = checks.verify(BuildResult(output=graph))
assert contract_results["valid-ArithmeticIR"].passed
```

Custom contracts can check domain-specific properties:

```python
from graphite import Contract, ContractResult


class HasVertices(Contract):
    def __init__(self):
        super().__init__(name="has-vertices")

    def evaluate(self, result):
        count = len(result.output.vertices)
        return ContractResult(
            passed=count > 0,
            output=result.output,
            metrics={"vertex_count": count},
        )
```

For complete examples, see [`examples/validation`](examples/validation),
[`examples/processor_tests`](examples/processor_tests), and the Loom-backed
[`examples/lowering`](examples/lowering) workflow.
