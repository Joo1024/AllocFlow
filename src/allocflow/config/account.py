def account_contract(plan):
    raw = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else plan
    return dict(
        report_currency=raw["report_currency"],
        instruments={
            i["id"]: {k: i[k] for k in [
                "symbol", "kind", "currency", "calendar",
                "price_mode", "pricing", "quantity_step",
            ]} for i in raw["instruments"]
        },
        budgets={b["id"]: b["currency"] for b in raw["budgets"]},
    )
