from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from allocflow.config.common import Fraction, Identifier, MoneySpec, NonNegative, Spec


class DistributionSpec(Spec):
    budget: Identifier
    weight: Fraction


class CashflowSpec(Spec):
    id: Identifier
    direction: Literal["deposit", "withdrawal"]
    frequency: Literal["once", "monthly"]
    start: date
    end: date
    money: MoneySpec
    annual_growth: NonNegative
    paused_months: tuple[str, ...]
    distributions: tuple[DistributionSpec, ...]

    @model_validator(mode="after")
    def valid_flow(self):
        if self.end < self.start:
            raise ValueError("cashflow end precedes start")
        if self.frequency == "once" and self.start != self.end:
            raise ValueError("once cashflow must have start == end")
        if self.direction == "deposit":
            if sum(d.weight for d in self.distributions) != 1:
                raise ValueError("deposit distributions must sum to 1")
        elif self.distributions:
            raise ValueError("withdrawal cannot have deposit distributions")
        if len({d.budget for d in self.distributions}) != len(self.distributions):
            raise ValueError("duplicate distribution budget")
        for month in self.paused_months:
            date.fromisoformat(month + "-01")
        return self


class WithdrawalSpec(Spec):
    cash_budgets: tuple[Identifier, ...] = Field(min_length=1)
    sell_order: tuple[Identifier, ...]
    proceeds_budget: Identifier
    shortfall: Literal["partial", "reject"]
