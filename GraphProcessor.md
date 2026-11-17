# Graph processor

`GraphProcessor` turns an AQL **select** pattern into a query graph, finds
matches in an `HGraph`, and can replace every eligible match with an AQL
**rewrite** graph. It changes the supplied graph in place.

```python
from graphite import GraphProcessor

processor = GraphProcessor(snapshot=False)
result = processor.run(
    graph,
    select="a => b => c",
    rewrite="a => c",
)
```

`result` contains:

- `matches`: dictionaries of AQL identifier to host-graph vertex ID;
- `pattern`: the parsed Heterograph `QGraph` for `select`;
- `modified`: whether the graph changed.

For the example above, a host path `0 → 1 → 2` yields
`{"a": 0, "b": 1, "c": 2}` and becomes `0 → 2`. The vertex matched as `b`
is removed because it does not occur on the rewrite's right-hand side.

## AQL as used by Graphite

AQL describes a directed query graph. Identifiers start with a letter and may
contain letters, digits, and underscores.

| Form | Meaning |
| --- | --- |
| `a` | A named vertex. |
| `a => b` | A directed edge from `a` to `b`. |
| `a ={weight: 2}> b` | A directed edge with AQL arguments. |
| `a{kind: "Input"}` | A vertex with AQL arguments. |
| `(a \| b) => c` | Two edges: `a => c` and `b => c`. |
| `0` | The empty graph. |
| `a => b; c => d` | The union of two graph clauses. |

Parenthesized groups connect every sink on the left to every source on the
right. Consequently, `(a | b) => (c | d)` creates four directed edges.
Repeated identifiers refer to the same query vertex, so clauses can assemble a
non-linear graph:

```text
(left | right) => join; join => output
```

The parser accepts positional values, strings, integers, floats, booleans, and
key/value pairs. It hands them to `QGraph` callbacks as positional and keyword
arguments.

### Important GraphProcessor distinction

AQL structure is always significant. Ordinary AQL attributes are **not**
automatically predicates in Graphite's default `IsoMatchStrategy`: its default
vertex, edge, and whole-match checks accept everything. Use `where` for
metadata constraints, or provide a custom `MatchStrategy` that interprets AQL
arguments.

```python
def is_dense_with_parameter_inputs(g, x, w, b, d):
    return (
        g.pmap[d].get("_type") == "Dense"
        and g.pmap[(w, d)].get("_type") == "parameter"
    )

processor.run(
    graph,
    select="(x | w | b) => d",
    where=is_dense_with_parameter_inputs,
)
```

`where` is called only after a structural match has been found. It receives the
host graph as `g` plus the named bindings as keyword arguments.

## Matching

By default, `GraphProcessor` uses `IsoMatchStrategy`. It parses `select`
into a `QGraph`, then asks graph-tool for induced directed subgraph
isomorphisms. Graphite subsequently applies these checks:

1. `MatchStrategy.vx_check` for every bound vertex;
2. `MatchStrategy.eg_check` for every pattern edge;
3. `MatchStrategy.check` for the complete binding;
4. `where(g, **binding)`, when supplied.

The base strategy implements the first three checks as unconditional success;
subclasses can implement semantic matching without changing the processor.

Matches are deduplicated by their set of host vertices (`deduplicate=True` by
default). This deliberately treats two bindings that cover the same vertex set
as one match. `max_n` limits the result list after deduplication; `max_n=0`
means no limit.

`DfsMatchStrategy` is an alternative for tree graphs. It uses Heterograph's DFS
query processor and is not the default. It is unsuitable for cyclic or
non-tree host graphs. Its distance callback expects an `xdist` edge property;
the stock strategy does not populate that property from AQL arguments, so use a
custom strategy that implements `eg_annotation` before relying on `xdist`.

## Rewrite model

The rewrite is another AQL graph. Graphite compares identifiers and edges in
the select graph (LHS) with those in the rewrite graph (RHS).

```text
select:  a => b => c
rewrite: a => x => c
```

| Category | Rule | Example |
| --- | --- | --- |
| Preserved vertex | Identifier appears on both sides. | `a`, `c` |
| Deleted vertex | Identifier appears only on the LHS. | `b` |
| Created vertex | Identifier appears only on the RHS. | `x` |
| Preserved edge | Same named endpoints appear on both sides. | none above |
| Removed edge | LHS edge absent from RHS. | `a => b`, `b => c` |
| Added edge | RHS edge absent from LHS. | `a => x`, `x => c` |

RHS-only vertices are allocated with empty metadata. A rewrite normally uses a
`finalize` callback to initialize their property maps and any new edge metadata.

### Single-pass and disjointness rule

The processor obtains all matches before mutating the graph. If a rewrite is
requested, no two selected matches may share a host vertex. Otherwise it raises
`RuntimeError` before applying any rewrite. This prevents one rewrite from
invalidating another precomputed binding.

The processor performs one pass only. A caller that wants a fixed point must
call it again, or use a pipeline loop such as Loom's `Pipeline.repeat()`.

### Mutation order

For each disjoint binding, Graphite:

1. checks that all matched vertices still exist;
2. creates RHS-only vertices;
3. adds RHS-only internal edges;
4. validates and applies permitted boundary rewires;
5. invokes `finalize`, if supplied;
6. removes LHS-only edges whose endpoints are both preserved;
7. deletes LHS-only vertices (and therefore their incident edges).

`finalize(g, **binding)` receives both preserved and newly created vertex IDs.
It must return an actual `bool`; `True` contributes to `modified`. It may add
metadata or other safe changes, but it may not delete a vertex or edge that the
rewrite still needs to remove. This protects the planned cleanup and makes
structural rewrite ownership unambiguous.

## Boundary rewiring

Deleting a matched vertex normally removes all of its incident edges. A rewrite
can explicitly preserve its connections to vertices outside the matched
subgraph by annotating an RHS receiver:

```text
receiver {rewire: deleted}
receiver {rewire_in: deleted}
receiver {rewire_out: deleted}
```

| Annotation | Effect |
| --- | --- |
| `rewire: old` | Redirect both external incoming and outgoing edges of `old` to/from the receiver. |
| `rewire_in: old` | Redirect external incoming edges `external => old` to `external => receiver`. |
| `rewire_out: old` | Redirect external outgoing edges `old => external` to `receiver => external`. |

The annotated identifier is the receiver and must be present on the RHS. The
referenced identifier is the source and must be LHS-only, so it will be deleted.
At most one rewire annotation may appear on a receiver.

Only **boundary** edges are rewired. If an edge comes from a preserved matched
vertex, the rewrite must state the corresponding RHS edge explicitly. Graphite
rejects a rewire that would silently create an internal edge. When it creates a
rewired boundary edge, it copies the original edge's property map.

```text
select:  a => b => c
rewrite: a => x {rewire: b} => c
```

Here `b` is deleted, `x` is created, the explicit RHS retains the internal
`a => x => c` path, and any external edges incident to `b` are redirected to
`x`.

## Dense lowering walkthrough

[`examples/lowering/lower_dense_task.py`](examples/lowering/lower_dense_task.py)
uses GraphProcessor to lower one NN-IR `Dense` layer into primitive OP-IR
operations.

The select pattern is:

```text
(x | w | b) => d
```

It matches three inputs to the same Dense vertex: data `x`, weight `w`, and
bias `b`. The `_where` callback then enforces the actual IR semantics:
vertex types, the `data`/`parameter` edge types, and each operand index.

The rewrite is:

```text
(x | w) => matmul => bias_add => act {rewire_out: d}; b => bias_add
```

Semicolon composition adds the `b => bias_add` branch to the main chain. The
identifier comparison produces this mapping:

| LHS | RHS | Outcome |
| --- | --- | --- |
| `x`, `w`, `b` | `x`, `w`, `b` | Preserved input vertices |
| `d` | absent | Delete the Dense vertex |
| absent | `matmul`, `bias_add`, `act` | Create primitive operation vertices |

`rewire_out: d` transfers the Dense layer's external consumers to `act`,
which becomes the new output of the lowered subgraph. The callback initializes
the three created operation vertices, retypes `w` and `b` as `Weight` and
`Bias`, and assigns metadata to every new edge.

Adjacent Dense layers can share a vertex, so two such matches overlap. The
example passes `max_n=1` to select one match per call, then relies on
`Pipeline.repeat()` to lower the next layer in a later pass. After a successful
rewrite it updates the graph-level IR type and validates the final graph with a
`GraphSchemaContract`.

## Snapshots and errors

`GraphProcessor(snapshot=True)` is the default. When a rewrite is requested it
records the graph before and after the pass in Heterograph's `WebView`; call
`snapshot_view()` to display them. Use `snapshot=False` in headless scripts
and tests.

Common deliberate errors are overlapping rewrite matches, a rewire source that
is not deleted, a missing explicit internal RHS edge created by rewiring, and a
`finalize` callback that returns a non-boolean or removes planned cleanup.


