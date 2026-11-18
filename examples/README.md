# Graphite examples

These examples use Graphite directly. Install Graphite as described in the
[main README](../README.md), then run the commands below from the repository root.

## Schema validation

```bash
python examples/validation/main.py
```

The [schema](validation/nn_ir.py) describes a small neural-network IR using
Pydantic models for vertex, edge, and quantization metadata, plus structural
rules. The [example](validation/main.py) builds a chain containing Input,
Embedding, ReLU, SumPool, Dense, and Output vertices, updates a vertex through
`GraphSchema`, and validates the graph. A successful run prints
`OK  NN-IR: 0 issues`.

## Graph matching and rewriting

```bash
python examples/processor_tests/main.py
```

This executable collection exercises `GraphProcessor` on small Heterograph
graphs. It covers pattern matching, `where` filters, rewrite passes, vertex
creation and `finalize` callbacks, rewiring, and rejection of overlapping or
invalid rewrites. Each case prints `PASS` or `FAIL`, followed by a count; the
script exits with a nonzero status if a case fails. See
[GraphProcessor.md](../GraphProcessor.md) for the pattern language and rewrite
semantics.

## Standalone lowering

```bash
python examples/lowering/main.py
```

This minimal example constructs an Input → Dense → Output graph and lowers each
Dense vertex into MatMul → Activation vertices. A `where` callback selects
Dense vertices, a `finalize` callback labels the new vertices, and the script
repeats one rewrite at a time until no more matches remain. It checks the
result and prints the vertex types. The example illustrates graph rewriting;
it does not import a model or implement numerical Dense operations.
