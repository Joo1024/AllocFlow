from decimal import ROUND_CEILING, ROUND_DOWN
from typing import Protocol

from allocflow.accounting.book import Book
from allocflow.domain.types import ZERO, BuyIntent, Intent, SellIntent, TransferIntent


def floor_step(value, step):
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def ceil_step(value, step):
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


class ExecutionModel(Protocol):
    def fee(self, book: Book, nominal, currency, day): ...

    def execute(self, book: Book, intent: Intent, day) -> bool: ...


class CashExecution:
    def fee(self, book, nominal, currency, day):
        spec = book.plan.execution.fee
        fixed = spec.fixed * book.market.fx(spec.fixed_currency, currency, day)
        variable = nominal * spec.proportional
        return fixed + variable if spec.model == "fixed_plus_proportional" else max(fixed, variable)

    def execute(self, book, intent, day):
        if isinstance(intent, TransferIntent):
            return self._transfer(book, intent, day)
        spec = book.instruments[intent.instrument]
        budget = book.budgets[intent.budget]
        price = book.market.price(spec.id, day, visible=spec.pricing == "available_nav")
        rate = book.market.fx(spec.currency, budget.currency, day)
        spread = book.plan.execution.fx_spread if spec.currency != budget.currency else ZERO
        before = book.value(day)[0]
        if isinstance(intent, BuyIntent):
            cap = min(intent.maximum_cash, book.spendable(intent.budget))
            native_cap = cap * (1 - spread) / rate
            fixed = self.fee(book, ZERO, spec.currency, day)
            proportional = book.plan.execution.fee.proportional
            if book.plan.execution.fee.model == "max":
                nominal = min(native_cap - fixed, native_cap / (1 + proportional))
            else:
                nominal = (native_cap - fixed) / (1 + proportional)
            quantity = floor_step(max(nominal, ZERO) / price, spec.quantity_step)
            nominal = quantity * price
            fee = self.fee(book, nominal, spec.currency, day)
            debit = ceil_step((nominal + fee) * rate / (1 - spread), book.plan.execution.cash_step)
            if quantity <= 0 or debit > cap:
                return self._reject(book, intent, day, "insufficient_budget_or_quantity_step")
            book.change_cash(intent.budget, -debit)
            book.state.holdings[spec.id] = book.state.holdings.get(spec.id, ZERO) + quantity
            side, cash_change = "buy", -debit
        elif isinstance(intent, SellIntent):
            quantity = floor_step(intent.quantity, spec.quantity_step)
            if quantity <= 0 or intent.quantity > book.sellable(spec.id):
                return self._reject(book, intent, day, "invalid_or_excess_inventory")
            nominal = quantity * price
            fee = self.fee(book, nominal, spec.currency, day)
            credit = floor_step(
                (nominal - fee) * rate * (1 - spread), book.plan.execution.cash_step
            )
            if credit <= 0:
                return self._reject(book, intent, day, "fees_exceed_proceeds")
            book.change_cash(intent.budget, credit)
            book.state.holdings[spec.id] -= quantity
            side, cash_change = "sell", credit
        else:
            raise TypeError(f"unsupported intent {type(intent)}")
        fee_report = fee * book.fx(spec.currency, day)
        loss = before - book.value(day)[0]
        book.state.record(
            day,
            "trade",
            intent.rule_id,
            "filled",
            side=side,
            instrument=spec.id,
            budget=intent.budget,
            quantity=quantity,
            price=price,
            currency=spec.currency,
            cash_change=cash_change,
            fee=fee,
            fee_report=fee_report,
            fx_and_rounding_report=loss - fee_report,
            reason=intent.reason,
        )
        book.assert_invariants()
        return True

    def _transfer(self, book, intent, day):
        source = book.budgets[intent.source].currency
        target = book.budgets[intent.destination].currency
        available = book.spendable(intent.source)
        if intent.amount <= 0 or intent.amount > available:
            return self._reject(book, intent, day, "insufficient_transfer_budget")
        spread = book.plan.execution.fx_spread if source != target else ZERO
        credit = floor_step(
            intent.amount * book.market.fx(source, target, day) * (1 - spread),
            book.plan.execution.cash_step,
        )
        loss = intent.amount * book.fx(source, day) - credit * book.fx(target, day)
        book.change_cash(intent.source, -intent.amount)
        book.change_cash(intent.destination, credit)
        book.state.record(
            day,
            "transfer",
            intent.rule_id,
            "filled",
            source=intent.source,
            destination=intent.destination,
            amount=intent.amount,
            credit=credit,
            fx_and_rounding_report=loss,
            reason=intent.reason,
        )
        book.assert_invariants()
        return True

    @staticmethod
    def _reject(book, intent, day, reason):
        book.state.record(
            day, "execution", intent.rule_id, "rejected", reason=reason, intent=repr(intent)
        )
        return False
