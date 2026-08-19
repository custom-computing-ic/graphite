"""Contracts for validating objects produced by graph workflows."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol


class ResultLike(Protocol):
    """The minimal result interface accepted by a contract."""

    output: Any


class ContractException(Exception):
    """Raised when a contract rejects an execution result."""

    def __init__(
        self,
        result: ResultLike,
        contract_results: dict[str, ContractResult],
    ):
        self.result = result
        self.contract_results = contract_results
        self.failures = {
            name: contract_result
            for name, contract_result in contract_results.items()
            if not contract_result.passed
        }
        super().__init__(
            f"{len(self.failures)} contract(s) failed: {list(self.failures)}"
        )


@dataclass(frozen=True)
class ContractResult:
    """Result of verifying one execution result."""

    passed: bool
    output: Any = None
    failures: list[Any] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.passed) is not bool:
            raise TypeError(
                "ContractResult.passed must be an actual bool, "
                f"got {type(self.passed).__name__}."
            )


class Contract(ABC):
    """Human-defined acceptance criteria for an object with ``output``."""

    def __init__(self, *, name: str):
        if not name:
            raise ValueError("Contract must have a name.")
        self.name = name

    def verify(self, result: ResultLike) -> ContractResult:
        """Evaluate one explicit result-like object."""
        if not hasattr(result, "output"):
            raise TypeError("Contract.verify() requires an object with output.")
        contract_result = self.evaluate(result)
        if not isinstance(contract_result, ContractResult):
            raise RuntimeError(
                f"contract {self.name} returned {type(contract_result).__name__}; "
                "Contract.evaluate() must return ContractResult"
            )
        return contract_result

    @abstractmethod
    def evaluate(self, result: ResultLike) -> ContractResult:
        """Evaluate one explicit result-like object."""


class Verifier:
    """Run every Contract and aggregate the individual results."""

    def __init__(self, contracts: Iterable[Contract]):
        self.contracts = list(contracts)
        if not all(isinstance(contract, Contract) for contract in self.contracts):
            raise TypeError("contracts must contain only Contract instances.")

    def verify(self, result: ResultLike) -> dict[str, ContractResult]:
        """Run all contracts, retaining failures from each contract."""
        results: dict[str, ContractResult] = {}
        for contract in self.contracts:
            try:
                results[contract.name] = contract.verify(result)
            except Exception as error:
                results[contract.name] = ContractResult(
                    passed=False,
                    failures=[f"{type(error).__name__}: {error}"],
                )
        if not self.passed(results):
            raise ContractException(result, results)
        return results

    @staticmethod
    def passed(results: dict[str, ContractResult]) -> bool:
        """Return whether every Contract passed."""
        return all(result.passed for result in results.values())

