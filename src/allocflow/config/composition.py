from datetime import date
from typing import Annotated, Literal

from pydantic import Field, model_validator

from allocflow.config.common import Identifier, NonNegative, Number, Spec


class Predicate(Spec):
    kind: Literal["predicate"]
    metric: Literal["budget", "drawdown", "weight", "drift", "total_value"]
    reference: Identifier | None
    operator: Literal["lt", "le", "gt", "ge"]
    value: Number
    lookback_sessions: int | None = Field(ge=2)


class ConditionGroup(Spec):
    kind: Literal["all", "any"]
    conditions: tuple["Condition", ...] = Field(min_length=1)


Condition = Annotated[Predicate | ConditionGroup, Field(discriminator="kind")]
ConditionGroup.model_rebuild()


class RuleControl(Spec):
    rule: Identifier
    start: date
    end: date
    months: tuple[int, ...] = Field(min_length=1)
    condition: Condition | None
    cooldown_days: int = Field(ge=0)
    max_fires: int | None = Field(ge=1)
    rearm: Literal["level", "crossing"]
    rank: Literal["original", "underweight", "momentum"]
    ranking_lookback_sessions: int | None = Field(ge=2)
    max_assets: int | None = Field(ge=1)
    minimum_order: NonNegative
    maximum_deployment: NonNegative | None
    reserve_amount: NonNegative

    @model_validator(mode="after")
    def bounds(self):
        if self.end < self.start or any(m < 1 or m > 12 for m in self.months):
            raise ValueError("invalid control date/month schedule")
        if len(set(self.months)) != len(self.months):
            raise ValueError("duplicate schedule month")
        if self.rank == "momentum" and self.ranking_lookback_sessions is None:
            raise ValueError("momentum ranking requires lookback")
        return self
