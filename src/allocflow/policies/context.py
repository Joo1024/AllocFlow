from collections.abc import Mapping
from datetime import timedelta
from types import MappingProxyType

from allocflow.domain.types import ZERO, BuyIntent
from allocflow.policies.base import PolicyContext


def freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    return value


def make_context(book, day, rule_id):
    plan, state = book.plan, book.state
    observed = day - timedelta(days=1)
    total, holding_values, _ = book.value(observed, visible=True)
    available = dict(state.budgets)
    for pending in state.pending:
        if isinstance(pending.intent, BuyIntent):
            i = pending.intent
            available[i.budget] = available.get(i.budget, ZERO) - i.maximum_cash
    currencies = {
        plan.report_currency,
        *(i.currency for i in plan.instruments),
        *(b.currency for b in plan.budgets),
    }
    values = dict(
        day=day,
        total_value=total,
        report_currency=plan.report_currency,
        budgets=available,
        budget_currencies={b.id: b.currency for b in plan.budgets},
        budget_nodes={b.id: b.allocation_node for b in plan.budgets},
        holdings=dict(state.holdings),
        holding_values=holding_values,
        prices={i.id: book.market.price(i.id, observed, visible=True) for i in plan.instruments},
        fx_to_report={c: book.fx(c, observed) for c in currencies},
        instrument_currencies={i.id: i.currency for i in plan.instruments},
        targets=plan.allocation.leaves(),
        node_targets={n.id: n.leaves() for n in plan.allocation.nodes()},
        groups={g.id: g.instruments for g in plan.groups},
        histories={i.id: book.market.history(i.id, day) for i in plan.instruments},
        memory=state.rule_state.get(rule_id, {}),
        inflows=state.latest_inflows,
    )
    return PolicyContext(**{k: freeze(v) for k, v in values.items()})
