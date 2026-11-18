# Changelog

## 0.2.0

- Remove the generic contract API and graph-schema contract from Graphite.
  Generic contracts now belong to Loom; compiler-specific integration belongs
  in loom-projects. Imports of these classes from `graphite` must be updated.
- Move Loom-based compiler and agent examples out of Graphite, and add a
  standalone Graphite lowering example.
- Stop isomorphism matching after the requested number of accepted matches,
  and add tests for matching, schemas, and graph rewriting behavior.
- Move the Conda environment to the repository root and install Graphite in
  editable mode for development.
- Expand the GraphProcessor and example documentation, and move release and
  cleanup scripts into `scripts/`.

## 0.1.0

- first release


