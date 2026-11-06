from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from allocflow.config.common import Spec
from allocflow.domain.types import Intent


@dataclass(frozen=True)
class PolicyContext:
    day: date
    total_value: Decimal
    report_currency: str
    budgets: Mapping[str, Decimal]
    budget_currencies: Mapping[str, str]
    budget_nodes: Mapping[str, str]
    holdings: Mapping[str, Decimal]
    holding_values: Mapping[str, Decimal]
    prices: Mapping[str, Decimal]
    fx_to_report: Mapping[str, Decimal]
    instrument_currencies: Mapping[str, str]
    targets: Mapping[str, Decimal]
    node_targets: Mapping[str, Mapping[str, Decimal]]
    groups: Mapping[str, tuple[str, ...]]
    histories: Mapping[str, tuple[Decimal, ...]]
    memory: Mapping
    inflows: Mapping[str, Mapping[str, Decimal]]


@dataclass(frozen=True)
class Decision:
    intents: tuple[Intent, ...]
    explanation: str
    observed_state: Mapping
    accepted_state: Mapping


class Strategy(ABC):
    """Implement a trusted Python extension; never mutate account state."""

    @abstractmethod
    def evaluate(self, context: PolicyContext, parameters: Spec) -> Decision: ...


class StrategyRegistry:
    def __init__(self):
        self._entries: dict[str, tuple[Strategy, type[Spec]]] = {}

    def register(self, name: str, strategy: Strategy, parameter_model: type[Spec]):
        if name in self._entries:
            raise ValueError(f"strategy already registered: {name}")
        self._entries[name] = (strategy, parameter_model)

    def evaluate(self, name: str, context: PolicyContext, parameters: dict) -> Decision:
        if name not in self._entries:
            raise ValueError(
                f"unregistered strategy: {name}; register trusted Python code through SDK"
            )
        strategy, model = self._entries[name]
        return strategy.evaluate(context, model.model_validate(parameters))
