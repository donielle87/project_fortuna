"""Rule-change log loader (metadata/rule_change_log.csv)."""

from pathlib import Path

from fortuna.schemas.csv_io import load_csv
from fortuna.schemas.sources import RuleChange

DEFAULT_PATH = Path("metadata/rule_change_log.csv")


def load_rule_change_log(path: str | Path = DEFAULT_PATH) -> list[RuleChange]:
    return load_csv(path, RuleChange)
