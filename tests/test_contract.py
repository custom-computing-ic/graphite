from dataclasses import dataclass

import pytest

from graphite import Contract, ContractException, ContractResult, Verifier


@dataclass
class Result:
    output: object


class Equals(Contract):
    def __init__(self, expected):
        super().__init__(name=f"equals-{expected}")
        self.expected = expected

    def evaluate(self, result):
        return ContractResult(passed=result.output == self.expected)


def test_verifier_accepts_a_passing_contract():
    results = Verifier([Equals(3)]).verify(Result(3))
    assert results["equals-3"].passed


def test_verifier_reports_a_failing_contract():
    with pytest.raises(ContractException) as exc:
        Verifier([Equals(3)]).verify(Result(4))
    assert list(exc.value.failures) == ["equals-3"]
