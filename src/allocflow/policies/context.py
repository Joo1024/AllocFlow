from collections.abc import Mapping
from datetime import timedelta
from types import MappingProxyType

from allocflow.accounting.planning import reserve_floor
from allocflow.domain.types import ZERO
from allocflow.policies.base import BudgetSnapshot, PolicyContext


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
    snapshots = {
        b.id: BudgetSnapshot(
            balance=state.budgets.get(b.id, ZERO),
            pending=state.budgets.get(b.id, ZERO) - book.uncommitted(b.id),
            reserve=reserve_floor(plan, b.id, day, purpose="investment"),
            spendable=max(
                book.uncommitted(b.id) - reserve_floor(plan, b.id, day, purpose="investment"),
                ZERO,
            ),
        )
        for b in plan.budgets
    }
    available = {key: snapshot.spendable for key, snapshot in snapshots.items()}
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
        budget_snapshots=snapshots,
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
