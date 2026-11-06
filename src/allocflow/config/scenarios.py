from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from allocflow.config.common import Identifier, Number, Spec


class ScenarioSpec(Spec):
    schema_version: Literal["1"]
    method: Literal["joint_block", "fixed_shock"]
    training_start: date
    training_end: date
    paths: int = Field(ge=1)
    root_seed: int = Field(ge=0)
    block_sessions: int = Field(ge=1)
    workers: int = Field(ge=1)
    shock_date: date | None
    asset_shocks: dict[Identifier, Number]
    fx_shocks: dict[str, Number]

    @model_validator(mode="after")
    def validate_shocks(self):
        if self.training_end < self.training_start:
            raise ValueError("training end precedes start")
        if any(v <= -1 for v in [*self.asset_shocks.values(), *self.fx_shocks.values()]):
            raise ValueError("shock returns must exceed -100%")
        if self.method == "fixed_shock" and self.shock_date is None:
            raise ValueError("fixed_shock requires shock_date")
        return self
