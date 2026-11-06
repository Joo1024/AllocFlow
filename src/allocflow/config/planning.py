from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from allocflow.config.common import Currency, Identifier, NonNegative, Number, Spec


class PhaseSpec(Spec):
    id: Identifier
    kind: Literal["accumulation", "retirement", "transition"]
    start: date
    end: date
    cashflows: tuple[Identifier, ...]
    rules: tuple[Identifier, ...]


class InflationSpec(Spec):
    annual_rate: Number = Field(gt=-1)
    base_date: date
    day_count: Literal["ACT/365F", "ACT/360"]
    indexed_cashflows: tuple[Identifier, ...]


class WithdrawalBounds(Spec):
    currency: Currency
    minimum: NonNegative
    maximum: NonNegative
    inflation_adjusted: bool


class ReserveSpec(Spec):
    budget: Identifier
    amount: NonNegative
    inflation_adjusted: bool
    protect_from_withdrawals: bool


class GoalSpec(Spec):
    id: Identifier
    date: date
    currency: Currency
    amount: NonNegative
    inflation_adjusted: bool


class PlanningSpec(Spec):
    phases: tuple[PhaseSpec, ...] = Field(min_length=1)
    inflation: InflationSpec
    withdrawal_bounds: WithdrawalBounds | None
    reserves: tuple[ReserveSpec, ...]
    goals: tuple[GoalSpec, ...]

    @model_validator(mode="after")
    def ordered(self):
        previous = None
        for phase in self.phases:
            if phase.end < phase.start or (previous is not None and phase.start <= previous):
                raise ValueError("phases must be ordered and non-overlapping")
            previous = phase.end
        if (
            self.withdrawal_bounds
            and self.withdrawal_bounds.maximum < self.withdrawal_bounds.minimum
        ):
            raise ValueError("withdrawal maximum below minimum")
        for items in (self.phases, self.goals):
            if len({x.id for x in items}) != len(items):
                raise ValueError("duplicate planning id")
        if len({x.budget for x in self.reserves}) != len(self.reserves):
            raise ValueError("duplicate reserve budget")
        return self
