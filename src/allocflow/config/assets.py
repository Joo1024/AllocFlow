from typing import Literal

from pydantic import Field, model_validator

from allocflow.config.common import Currency, Fraction, Identifier, NonNegative, Positive, Spec


class InstrumentSpec(Spec):
    id: Identifier
    symbol: str
    kind: Literal["equity", "etf", "mutual_fund", "cash_equivalent"]
    currency: Currency
    calendar: str
    price_mode: Literal["total_return_synthetic", "provider_adjusted_synthetic"]
    quantity_step: Positive
    execution_delay_sessions: int = Field(ge=0)
    pricing: Literal["session_close", "available_nav"]

    @model_validator(mode="after")
    def fund_pricing(self):
        if self.kind == "mutual_fund" and self.pricing != "available_nav":
            raise ValueError("mutual_fund requires explicit available_nav research pricing")
        return self


class AllocationNode(Spec):
    id: Identifier
    weight: Fraction
    instrument: Identifier | None
    children: tuple["AllocationNode", ...]

    @model_validator(mode="after")
    def structure(self):
        if (self.instrument is None) == (not self.children):
            raise ValueError("node must be either an instrument leaf or a non-empty branch")
        if self.children and sum(c.weight for c in self.children) != 1:
            raise ValueError("child weights must sum to 1 exactly")
        return self

    def leaves(self, parent_weight=1):
        weight = parent_weight * self.weight
        if self.instrument is not None:
            return {self.instrument: weight}
        result = {}
        for child in self.children:
            for key, value in child.leaves(weight).items():
                if key in result:
                    raise ValueError(f"duplicate allocation instrument: {key}")
                result[key] = value
        return result

    def nodes(self):
        return [self, *(node for child in self.children for node in child.nodes())]


class GroupSpec(Spec):
    id: Identifier
    instruments: tuple[Identifier, ...] = Field(min_length=1)


class BudgetSpec(Spec):
    id: Identifier
    currency: Currency
    allocation_node: Identifier
    annual_interest_rate: NonNegative
