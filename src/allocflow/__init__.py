"""AllocFlow: cash-flow-aware investment plans."""

__version__ = "0.1.0"


def load_plan(path):
    from allocflow.config.loader import load_plan as load

    return load(path)


def run_plan(plan, dataset, *, strategies=None):
    from allocflow.application.service import run_plan as run

    return run(plan, dataset, strategies=strategies)
