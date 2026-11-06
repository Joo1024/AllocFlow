import hashlib
import json
from copy import copy
from datetime import date
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pandera.pandas as pa


from allocflow.domain.market import Observation


class DataError(ValueError):
    pass


class MarketDataset:
    def __init__(self, prices, fx, *, metadata, max_stale_days):
        self.prices = prices
        self.rates = fx
        self.metadata = metadata
        self.base_currency = metadata["base_currency"]
        self.dataset_id = metadata["dataset_id"]
        self.max_stale_days = max_stale_days

    def with_staleness_policy(self, max_stale_days):
        result = copy(self)
        result.max_stale_days = max_stale_days
        return result

    def price_observations(self, instrument):
        return self.prices.get(instrument, ())

    def fx_observations(self, currency):
        return self.rates.get(currency, ())

    def fx_currencies(self):
        return tuple(sorted(self.rates))

    def export_artifacts(self):
        return dict(getattr(self, "artifacts", {}))

    def _latest(self, rows, day, *, visible, key):
        found = [r for r in rows if r.date <= day and (not visible or r.available_on <= day)]
        if not found:
            raise DataError(f"no {'visible ' if visible else ''}data for {key} on {day}")
        row = max(found, key=lambda r: r.date)
        if (day - row.date).days > self.max_stale_days:
            raise DataError(f"stale data for {key}: {row.date} -> {day}")
        return row.value

    def price(self, instrument, day, *, visible=False):
        return self._latest(self.prices.get(instrument, ()), day, visible=visible, key=instrument)

    def fx(self, source, target, day):
        if source == target:
            return Decimal(1)

        def rate(currency):
            if currency == self.base_currency:
                return Decimal(1)
            return self._latest(
                self.rates.get(currency, ()), day, visible=True, key=f"FX:{currency}"
            )

        return rate(source) / rate(target)

    def history(self, instrument, before):
        return tuple(
            r.value
            for r in self.prices.get(instrument, ())
            if r.date < before and r.available_on < before
        )

    @classmethod
    def load(cls, path, *, max_stale_days):
        path = Path(path)
        metadata = json.loads((path / "manifest.json").read_text())
        required = {
            "schema_version",
            "base_currency",
            "source",
            "availability_basis",
            "files",
            "instruments",
        }
        if not required <= metadata.keys() or metadata["schema_version"] != "1":
            raise DataError("invalid dataset manifest")
        if set(metadata["files"]) != {"prices.csv", "fx.csv"}:
            raise DataError("dataset requires exactly prices.csv and fx.csv")
        for name, expected in metadata["files"].items():
            digest = hashlib.sha256((path / name).read_bytes()).hexdigest()
            if digest != expected:
                raise DataError(f"dataset file hash mismatch: {name}")
        canonical = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
        metadata["dataset_id"] = hashlib.sha256(canonical.encode()).hexdigest()
        prices = cls._read_table(path / "prices.csv", "instrument")
        fx = cls._read_table(path / "fx.csv", "currency")
        result = cls(prices, fx, metadata=metadata, max_stale_days=max_stale_days)
        result.artifacts = {
            name: (path / name).read_bytes() for name in ["manifest.json", "prices.csv", "fx.csv"]
        }
        return result

    @staticmethod
    def _read_table(path, key):
        frame = pd.read_csv(path, dtype=str).reset_index(drop=True)
        schema = pa.DataFrameSchema(
            {
                name: pa.Column(str, nullable=False)
                for name in [key, "date", "available_on", "value"]
            },
            strict=True,
            unique=[key, "date"],
        )
        try:
            schema.validate(frame, lazy=True)
        except (pa.errors.SchemaError, pa.errors.SchemaErrors) as exc:
            raise DataError(f"{path.name}: {exc}") from exc
        numeric = pd.to_numeric(frame["value"], errors="raise")
        if not (np.isfinite(numeric).all() and (numeric > 0).all()):
            raise DataError(f"{path.name}: prices/rates must be positive finite numbers")
        result = {}
        for row in frame.to_dict("records"):
            effective = date.fromisoformat(row["date"])
            available = date.fromisoformat(row["available_on"])
            if available < effective:
                raise DataError("available_on cannot precede effective date")
            result.setdefault(row[key], []).append(
                Observation(effective, available, Decimal(row["value"]))
            )
        return {k: tuple(sorted(v, key=lambda r: r.date)) for k, v in result.items()}


def save_dataset(path, prices, fx, metadata):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    prices.to_csv(path / "prices.csv", index=False)
    fx.to_csv(path / "fx.csv", index=False)
    metadata = dict(metadata)
    metadata["files"] = {
        name: hashlib.sha256((path / name).read_bytes()).hexdigest()
        for name in ["prices.csv", "fx.csv"]
    }
    (path / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
