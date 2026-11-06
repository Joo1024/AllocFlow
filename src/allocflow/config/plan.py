from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from allocflow.config.assets import AllocationNode, BudgetSpec, GroupSpec, InstrumentSpec
from allocflow.config.cashflows import CashflowSpec, WithdrawalSpec
from allocflow.config.common import Currency, NonNegative, Number, Positive, Spec
from allocflow.config.rules import BudgetCapRule, CustomRule, InvestRule, RebalanceRule, RuleSpec


class FeeSpec(Spec):
    model: Literal["fixed_plus_proportional", "max"]
    fixed: NonNegative
    fixed_currency: Currency
    proportional: NonNegative


class ExecutionSpec(Spec):
    fee: FeeSpec
    cash_step: Positive
    fx_spread: NonNegative = Field(lt=1)
    max_stale_days: int = Field(ge=0)
    interest_day_count: Literal["ACT/365F", "ACT/360"]


class AnalysisSpec(Spec):
    frequency: Literal["daily", "monthly"]
    periods_per_year: Positive
    risk_free_annual: Number = Field(gt=-1)
    xirr_lower: Number = Field(gt=-1)
    xirr_upper: Positive
    xirr_grid_size: int = Field(ge=10)
    xirr_day_count: Literal["ACT/365F", "ACT/360"]
    xirr_root_tolerance: Positive
    xirr_npv_tolerance: Positive


class PlanSpec(Spec):
    schema_version: Literal["1"]
    name: str = Field(min_length=1)
    start: date
    end: date
    report_currency: Currency
    decision_calendar: str
    instruments: tuple[InstrumentSpec, ...] = Field(min_length=1)
    allocation: AllocationNode
    groups: tuple[GroupSpec, ...]
    budgets: tuple[BudgetSpec, ...] = Field(min_length=1)
    cashflows: tuple[CashflowSpec, ...]
    rules: tuple[RuleSpec, ...]
    withdrawal: WithdrawalSpec | None
    execution: ExecutionSpec
    analysis: AnalysisSpec

    @model_validator(mode="after")
    def business_contract(self):
        if self.end < self.start:
            raise ValueError("plan end precedes start")
        if self.analysis.xirr_lower >= self.analysis.xirr_upper:
            raise ValueError("invalid XIRR search domain")
        collections: list = [
            self.instruments,
            self.groups,
            self.budgets,
            self.cashflows,
            self.rules,
        ]
        for collection in collections:
            ids = [x.id for x in collection]
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate ids: {ids}")
        instruments = {x.id for x in self.instruments}
        budget_ids = {b.id for b in self.budgets}
        nodes = [n.id for n in self.allocation.nodes()]
        if len(nodes) != len(set(nodes)) or self.allocation.weight != 1:
            raise ValueError("allocation node ids must be unique and root weight must equal 1")
        if set(self.allocation.leaves()) != instruments:
            raise ValueError("allocation leaves must contain each instrument exactly once")
        for group in self.groups:
            if not set(group.instruments) <= instruments:
                raise ValueError(f"unknown instrument in group {group.id}")
            if len(set(group.instruments)) != len(group.instruments):
                raise ValueError(f"duplicate instrument in group {group.id}")
        for budget in self.budgets:
            if budget.allocation_node not in nodes:
                raise ValueError(f"unknown allocation node for budget {budget.id}")
        flow_ids = {f.id for f in self.cashflows}
        for flow in self.cashflows:
            if not {d.budget for d in flow.distributions} <= budget_ids:
                raise ValueError(f"unknown budget in cashflow {flow.id}")
            if flow.direction == "withdrawal" and self.withdrawal is None:
                raise ValueError("withdrawal cashflow requires withdrawal policy")
        group_ids = {g.id for g in self.groups}
        for rule in self.rules:
            refs: set[str] = set()
            if isinstance(rule, InvestRule):
                refs.add(rule.source_budget)
                if rule.selector.group not in group_ids:
                    raise ValueError(f"unknown selector group in {rule.id}")
                if rule.trigger.kind == "drawdown" and rule.trigger.instrument not in instruments:
                    raise ValueError(f"unknown signal instrument in {rule.id}")
            elif isinstance(rule, BudgetCapRule):
                refs.update([rule.source_budget, rule.destination_budget])
                if rule.source_budget == rule.destination_budget:
                    raise ValueError("budget cap source and destination must differ")
                if rule.inflow_reference not in flow_ids:
                    raise ValueError(f"unknown inflow reference in {rule.id}")
            elif isinstance(rule, RebalanceRule):
                refs.update([*rule.cash_budgets, rule.proceeds_budget])
                if rule.proceeds_budget not in rule.cash_budgets or len(
                    set(rule.cash_budgets)
                ) != len(rule.cash_budgets):
                    raise ValueError("rebalance proceeds budget must be in unique cash_budgets")
                if rule.target_node not in nodes:
                    raise ValueError(f"unknown rebalance node in {rule.id}")
            elif isinstance(rule, CustomRule):
                pass
            if not refs <= budget_ids:
                raise ValueError(f"unknown budget in rule {rule.id}")
        if self.withdrawal:
            w = self.withdrawal
            if w.proceeds_budget not in w.cash_budgets or len(set(w.cash_budgets)) != len(
                w.cash_budgets
            ):
                raise ValueError("withdrawal proceeds budget must be in unique cash_budgets")
            if not {*w.cash_budgets, w.proceeds_budget} <= budget_ids:
                raise ValueError("unknown withdrawal budget")
            if not set(w.sell_order) <= instruments:
                raise ValueError("withdrawal sell_order must contain instrument ids")
        return self
