from typing import Literal

from pydantic import BaseModel, Field

from graphite import GraphSchema


class Value(BaseModel):
    type_: Literal["Value"] = Field(alias="_type")
    value: int


class Data(BaseModel):
    type_: Literal["data"] = Field(alias="_type")


def test_schema_constructs_and_validates_a_graph():
    schema = GraphSchema("TestIR", vertex={"Value": Value}, edge={"data": Data})
    graph = schema.new_graph()
    a = schema.new_vertex(graph, "Value", value=1)
    b = schema.new_vertex(graph, "Value", value=2)
    schema.new_edge(graph, a, b, "data")
    assert schema.validate(graph).ok


def test_schema_reports_unknown_vertex_type():
    schema = GraphSchema("TestIR", vertex={"Value": Value})
    graph = schema.new_graph()
    vertex = graph.add_vx()
    graph.pmap[vertex] = {"_type": "Missing"}
    report = schema.validate(graph)
    assert not report.ok
    assert "unknown _type" in str(report)
