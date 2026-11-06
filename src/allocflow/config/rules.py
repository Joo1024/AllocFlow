from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from allocflow.config.common import Fraction, Identifier, NonNegative, Positive, Spec


class AlwaysTrigger(Spec):
    kind: Literal["always"]


class DrawdownTier(Spec):
    threshold: Fraction
    fraction: Fraction


class DrawdownTrigger(Spec):
    kind: Literal["drawdown"]
    instrument: Identifier
    lookback_sessions: int | None = Field(ge=2)
    rearm: Literal["monthly", "crossing", "new_peak"]
    tiers: tuple[DrawdownTier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def ordered_tiers(self):
        thresholds = [t.threshold for t in self.tiers]
        if thresholds != sorted(set(thresholds)):
            raise ValueError("drawdown tiers must have strictly increasing thresholds")
        return self


TriggerSpec = Annotated[AlwaysTrigger | DrawdownTrigger, Field(discriminator="kind")]


class SelectorSpec(Spec):
    group: Identifier
    method: Literal["proportional", "underweight"]
    max_assets: int | None = Field(ge=1)


class SizerSpec(Spec):
    fraction: Fraction
    minimum_budget: NonNegative


class RuleBase(Spec):
    id: Identifier
    schedule: Literal["initial", "monthly", "every_session"]


class InvestRule(RuleBase):
    kind: Literal["invest"]
    source_budget: Identifier
    trigger: TriggerSpec
    selector: SelectorSpec
    sizer: SizerSpec


class BudgetCapRule(RuleBase):
    kind: Literal["budget_cap"]
    source_budget: Identifier
    destination_budget: Identifier
    inflow_reference: Identifier
    multiple: Positive


class RebalanceRule(RuleBase):
    kind: Literal["rebalance"]
    target_node: Identifier
    cash_budgets: tuple[Identifier, ...] = Field(min_length=1)
    proceeds_budget: Identifier
    weight_basis: Literal["holdings", "budget_inclusive"]
    threshold_mode: Literal["absolute", "relative"]
    threshold: Fraction
    minimum_trade: NonNegative


class CustomRule(RuleBase):
    kind: Literal["custom"]
    strategy: Identifier
    parameters: dict[str, Any]


RuleSpec = Annotated[
    InvestRule | BudgetCapRule | RebalanceRule | CustomRule, Field(discriminator="kind")
]
