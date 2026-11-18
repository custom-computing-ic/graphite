# Graphite

Graphite is a Python toolkit for describing, validating, matching, and
rewriting Heterograph-based intermediate representations (IRs). Graphite is independent of workflow orchestration frameworks.

For pattern matching, rewrites, and examples, see the [GraphProcessor guide](GraphProcessor.md).

## Installation

### Conda (development)

From the repository root, create an environment with Graphite installed in editable mode. Changes to the source take effect immediately:

```bash
conda env create -f environment.yml
conda activate graphite
pytest
```

### pip

Graphite requires Python 3.10 or newer and `graph-tool`. For Ubuntu:  
```bash
apt-get install python3-graph-tool
```  

For other graph-tool installation options, see the [graph-tool installation documentation](https://graph-tool.skewed.de/installation.html).

Then install [graphite-ir from PyPI](https://pypi.org/project/graphite-ir/):

```bash
python -m pip install graphite-ir
```

## Examples

The runnable examples are in [`examples/`](examples). The validation,
processor, and lowering examples use Graphite directly; see the
[examples README](examples/README.md) for commands and descriptions.

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


The standalone lowering example is in [`examples/lowering`](examples/lowering).
