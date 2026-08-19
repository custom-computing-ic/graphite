"""Graph-IR schemas, matching, and rewriting built on Heterograph."""

from .processor import GraphProcessor
from .match_strategy import DfsMatchStrategy, IsoMatchStrategy, MatchStrategy
from .schema import GraphSchema, Issue, Severity, ValidationReport
from .schema_contract import GraphSchemaContract
from .contract import Contract, ContractException, ContractResult, Verifier

__all__ = [
    "GraphProcessor",
    "MatchStrategy",
    "IsoMatchStrategy",
    "DfsMatchStrategy",
    "GraphSchema",
    "Issue",
    "Severity",
    "ValidationReport",
    "GraphSchemaContract",
    "Contract",
    "ContractException",
    "ContractResult",
    "Verifier",
]
