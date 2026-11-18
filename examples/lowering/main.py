"""Lower a small graph using Graphite without a workflow framework."""

from heterograph import HGraph
from graphite import GraphProcessor


def lower(graph):
    """Replace each Dense vertex with MatMul and Activation vertices."""
    processor = GraphProcessor(snapshot=False)

    def is_dense(g, x, dense, y):
        return g.pmap[dense].get("_type") == "Dense"

    def initialize(g, x, dense, y, matmul, activation):
        g.pmap[matmul]["_type"] = "MatMul"
        g.pmap[activation]["_type"] = "Activation"
        return True

    while processor.run(
        graph, select="x => dense => y", where=is_dense,
        rewrite="x => matmul => activation => y", finalize=initialize, max_n=1,
    )["modified"]:
        pass
    return graph


def main():
    graph = HGraph()
    graph.add_vx(3)
    for vertex, kind in enumerate(("Input", "Dense", "Output")):
        graph.pmap[vertex]["_type"] = kind
    graph.add_edge(0, 1)
    graph.add_edge(1, 2)
    lower(graph)
    kinds = [graph.pmap[v]["_type"] for v in graph.vertices]
    assert "Dense" not in kinds and {"MatMul", "Activation"} <= set(kinds)
    print("Lowered graph:", kinds)


if __name__ == "__main__":
    main()
