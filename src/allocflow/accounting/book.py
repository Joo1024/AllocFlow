from decimal import Decimal

from allocflow.domain.types import ONE, ZERO, AccountState, BuyIntent, SellIntent


class Book:
    def __init__(self, plan, market, state: AccountState):
        self.plan = plan
        self.market = market
        self.state = state
        self.current_day = state.last_date
        self.budgets = {b.id: b for b in plan.budgets}
        self.instruments = {i.id: i for i in plan.instruments}

    def change_cash(self, budget, delta):
        currency = self.budgets[budget].currency
        balance = self.state.budgets.get(budget, ZERO) + delta
        if balance < 0:
            raise ValueError(f"negative budget: {budget}")
        self.state.budgets[budget] = balance
        self.state.cash[currency] = self.state.cash.get(currency, ZERO) + delta

    def uncommitted(self, budget):
        reserved = sum(
            (
                p.intent.maximum_cash
                for p in self.state.pending
                if isinstance(p.intent, BuyIntent) and p.intent.budget == budget
            ),
            ZERO,
        )
        return self.state.budgets.get(budget, ZERO) - reserved

    def spendable(self, budget, *, purpose="investment"):
        from allocflow.accounting.planning import reserve_floor

        floor = reserve_floor(self.plan, budget, self.current_day, purpose=purpose)
        return max(self.uncommitted(budget) - floor, ZERO)

    def value(self, day, *, visible=False):
        holdings = {
            key: quantity
            * self.market.price(
                key, day, visible=visible or self.instruments[key].pricing == "available_nav"
            )
            * self.fx(self.instruments[key].currency, day)
            for key, quantity in self.state.holdings.items()
            if quantity
        }
        cash = sum(
            (
                amount * self.fx(currency, day)
                for currency, amount in self.state.cash.items()
                if amount
            ),
            ZERO,
        )
        return sum(holdings.values(), ZERO) + cash, holdings, cash

    def fx(self, currency, day):
        return self.market.fx(currency, self.plan.report_currency, day)

    def nav(self, day):
        return (
            self.value(day)[0] / self.state.units
            if self.state.units
            else (self.state.last_nav if self.state.last_nav is not None else ONE)
        )

    def issue_units(self, report_amount, nav):
        if nav <= 0 and report_amount > 0:
            raise ValueError("cannot deposit into zero-NAV episode; create a new plan run")
        if nav > 0:
            self.state.units += report_amount / nav

    def sellable(self, instrument):
        reserved = sum(
            (
                p.intent.quantity
                for p in self.state.pending
                if isinstance(p.intent, SellIntent) and p.intent.instrument == instrument
            ),
            ZERO,
        )
        return self.state.holdings.get(instrument, ZERO) - reserved

    def assert_invariants(self):
        if any(self.sellable(i) < 0 for i in self.state.holdings):
            raise ArithmeticError("pending sells exceed inventory")
        if any(self.uncommitted(b.id) < 0 for b in self.plan.budgets):
            raise ArithmeticError("pending orders exceed available budget")
        for currency, actual in self.state.cash.items():
            assigned = sum(
                (
                    self.state.budgets.get(b.id, ZERO)
                    for b in self.plan.budgets
                    if b.currency == currency
                ),
                ZERO,
            )
            if abs(assigned - actual) > Decimal("1e-18"):
                raise ArithmeticError(
                    f"cash/budget mismatch for {currency}: {assigned} != {actual}"
                )
        if any(
            v < 0
            for v in [
                *self.state.cash.values(),
                *self.state.budgets.values(),
                *self.state.holdings.values(),
            ]
        ):
            raise ArithmeticError("negative cash, budget or inventory")
        if self.state.units < Decimal("-1e-18"):
            raise ArithmeticError("negative fund units")
