"""Rules engine — regime loading, draw->regime assignment, pooling guards."""

from fortuna.rules.assign import (
    AmbiguousRegimeError,
    IncompatibleMatrixError,
    NoRegimeError,
    UnverifiedBoundaryError,
    assert_poolable,
    assign_regime,
)
from fortuna.rules.registry import (
    RegimeIntegrityError,
    check_regime_integrity,
    load_regimes,
)
from fortuna.rules.rule_log import load_rule_change_log

__all__ = [
    "AmbiguousRegimeError",
    "IncompatibleMatrixError",
    "NoRegimeError",
    "RegimeIntegrityError",
    "UnverifiedBoundaryError",
    "assign_regime",
    "assert_poolable",
    "check_regime_integrity",
    "load_regimes",
    "load_rule_change_log",
]
