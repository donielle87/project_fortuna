"""Canonical CSV (de)serialization for pydantic metadata models.

Conventions:
- column order = model field declaration order
- empty cell -> None (pydantic then enforces required-ness)
- lists serialize as ';'-joined strings
- bools serialize as 'true'/'false'
- dates/datetimes serialize as ISO 8601
- Decimals serialize as plain strings
- enums serialize as their value
"""

import csv
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

M = TypeVar("M", bound=BaseModel)


def _serialize(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return ";".join(_serialize(v) for v in value)
    return str(value)


def load_csv(path: str | Path, model: type[M]) -> list[M]:
    """Load a CSV file into validated model instances."""
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows: list[M] = []
        for line_no, raw in enumerate(reader, start=2):
            data = {k: (v if v != "" else None) for k, v in raw.items() if k is not None}
            try:
                rows.append(model.model_validate(data))
            except Exception as exc:  # noqa: BLE001 - re-raise with location context
                raise ValueError(f"{path}:{line_no}: validation failed: {exc}") from exc
        return rows


def dump_csv(path: str | Path, rows: list[M]) -> None:
    """Write model instances to a canonical CSV (header + field order stable)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        fields = list(type(rows[0]).model_fields.keys())
    else:
        raise ValueError("dump_csv requires at least one row to infer header")
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({f: _serialize(getattr(row, f)) for f in fields})


def dump_empty_csv(path: str | Path, model: type[BaseModel]) -> None:
    """Write a header-only CSV for a registry with no rows yet."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(model.model_fields.keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        csv.DictWriter(fh, fieldnames=fields).writeheader()
