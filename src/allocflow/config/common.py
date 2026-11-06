from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Number = Annotated[Decimal, Field(allow_inf_nan=False)]
NonNegative = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
Positive = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
Fraction = Annotated[Decimal, Field(ge=0, le=1, allow_inf_nan=False)]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.:-]*$")]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class Spec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class MoneySpec(Spec):
    amount: NonNegative
    currency: Currency
