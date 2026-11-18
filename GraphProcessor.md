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

The call returns a dictionary with:

- `matches`: dictionaries of AQL identifier to host-graph vertex ID;
- `pattern`: the parsed Heterograph `QGraph` for `select`;
- `modified`: whether the graph changed.

`matches` records the bindings found before rewriting, so a matched vertex ID
may refer to a vertex that the rewrite subsequently deleted.

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
key/value pairs. It passes them to `QGraph` callbacks as positional and keyword
arguments. The default strategy annotation callbacks accept keyword arguments
only; using positional arguments requires a custom callback that accepts them.

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
as one match. Set `deduplicate=False` to retain the separate bindings. A
positive `max_n` limits accepted matches after filtering and deduplication;
zero or a negative value means no limit. The default isomorphism strategy stops
searching once it has enough accepted matches; DFS limits its completed results.

`DfsMatchStrategy` is an alternative for tree graphs. It uses Heterograph's DFS
query processor and is not the default. It is unsuitable for cyclic or
non-tree host graphs. Its distance callback expects an `xdist` edge property;
the stock strategy does not populate that property from AQL arguments, so use a
custom strategy that implements `eg_annotation` before relying on `xdist`.
Unlike the isomorphism strategy, DFS calls `check` but not `vx_check` or
`eg_check`; it passes `where` only the named bindings in its signature.

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
call it again in your application, optionally stopping when `modified` is false.

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
Use one rewire annotation per receiver.

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

## Standalone lowering walkthrough

[`examples/lowering/main.py`](examples/lowering/main.py) builds a small
`Input => Dense => Output` graph and lowers each `Dense` vertex into a
`MatMul => Activation` chain. Run it from the repository root:

```bash
python examples/lowering/main.py
```

The processor selects `x => dense => y`. The `where` callback checks that the
middle vertex has `_type` equal to `Dense`. The rewrite replaces it:

```text
select:  x => dense => y
rewrite: x => matmul => activation => y
```

The `finalize` callback labels the two created vertices and returns `True`.
The example uses `max_n=1` to avoid overlapping matches, then repeats the
pass until `modified` is false. It checks the resulting vertex types. This is
a graph-rewriting demonstration; it does not execute a numerical model or
validate the lowered graph against a schema.

## Snapshots and errors

`GraphProcessor(snapshot=True)` is the default. When a rewrite is requested it
records the graph before and after the pass in Heterograph's `WebView`; call
`snapshot_view()` to display them. Use `snapshot=False` in headless scripts
and tests.

Common errors include overlapping rewrite matches, a rewire source that is not
deleted, a missing explicit internal RHS edge, and a `finalize` callback that
returns a non-boolean or removes planned cleanup. Overlap is checked before
rewriting, but other errors can occur after mutation has begun. Rewrites are
not transactional: an exception does not roll back earlier changes. If the
original graph must be preserved on failure, operate on a copy.


